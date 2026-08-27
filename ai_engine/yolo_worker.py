#!/usr/bin/env python3
"""
YOLO Worker — Resource-page compliant
• Uses PTS from stream (not wall clock)
• Resets DeepSORT on scene discontinuity (cam_resets stream)
• Frame skip for CPU efficiency (Intel Iris: 4 workers, skip 3)
• Decoder warnings are non-fatal (already handled by ingestion)
• Does NOT use CAP_PROP_FPS for any timing
"""
import os, time, base64, json, uuid, logging
import cv2, numpy as np
import redis
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from event_schema import detection_event

log = logging.getLogger("yolo_worker")

REDIS_URL    = os.getenv("REDIS_URL",      "redis://localhost:6379")
YOLO_MODEL   = os.getenv("YOLO_MODEL",    "yolov8n.pt")
CONF         = float(os.getenv("DETECTION_CONF", "0.4"))
FRAME_SKIP   = int(os.getenv("FRAME_SKIP",   "3"))    # detect 1 in N frames
YOLO_WORKERS = int(os.getenv("YOLO_WORKERS", "4"))
TEST_MODE    = os.getenv("TEST_MODE", "false").lower() == "true"
PREFIX       = "test:" if TEST_MODE else ""
GROUP        = "test_ai_workers" if TEST_MODE else "ai_workers"
IN_STREAM    = f"{PREFIX}raw_frames"
RESET_STREAM = f"{PREFIX}cam_resets"
OUT_STREAM   = f"{PREFIX}detections"
OUT_MAX      = 5000

TARGET_CLS = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

# ── Inference resize: smaller = faster on CPU ────────────────────────────────
INFER_SIZE = int(os.getenv("INFER_SIZE", "416"))   # 416 < 640, faster on CPU


def _ensure_group(r: redis.Redis, stream: str, group: str):
    try:
        r.xgroup_create(stream, group, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass


def _decode_frame(data: dict) -> np.ndarray | None:
    try:
        buf = base64.b64decode(data[b"frame"])
        arr = np.frombuffer(buf, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None


class WorkerState:
    """Per-camera tracker state."""
    def __init__(self):
        self.tracker    = DeepSort(max_age=30, n_init=3)
        self.frame_ctr  = 0
        self.prev_pts   = None

    def reset(self):
        """Call on scene discontinuity."""
        self.tracker    = DeepSort(max_age=30, n_init=3)
        self.frame_ctr  = 0
        self.prev_pts   = None
        log.info("Tracker reset (scene discontinuity)")


def run():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [YOLO][%(levelname)s] %(message)s")
    log.info(f"Loading {YOLO_MODEL} (CPU, infer_size={INFER_SIZE}) …")
    model    = YOLO(YOLO_MODEL)
    r        = redis.from_url(REDIS_URL, decode_responses=False)
    consumer = f"yolo-{uuid.uuid4().hex[:8]}"

    _ensure_group(r, IN_STREAM,    GROUP)
    _ensure_group(r, RESET_STREAM, "reset_watchers")

    states: dict[str, WorkerState] = {}

    # Track the last reset-stream ID we processed
    last_reset_id = b"0"

    log.info(f"YOLO worker ready (skip={FRAME_SKIP}).")

    while True:
        # ── Poll cam_resets stream for discontinuity signals ─────────────────
        resets = r.xread({RESET_STREAM: last_reset_id}, count=20, block=0)
        if resets:
            for _, entries in resets:
                for msg_id, data in entries:
                    cam_id = data.get(b"cam_id", b"").decode()
                    if cam_id in states:
                        states[cam_id].reset()
                    last_reset_id = msg_id

        # ── Read frames ───────────────────────────────────────────────────────
        msgs = r.xreadgroup(GROUP, consumer, {IN_STREAM: ">"}, count=4, block=200)
        if not msgs:
            continue

        for _, entries in msgs:
            for msg_id, data in entries:
                try:
                    cam_id  = data.get(b"cam_id", b"").decode()
                    pts_ms  = int(data.get(b"pts_ms", b"0"))   # use PTS
                    source_ts = data.get(b"source_ts", b"")
                    ingested_at = data.get(b"ingested_at", b"")
                    stream_id = data.get(b"stream_id", b"")
                    frame   = _decode_frame(data)
                    if frame is None:
                        continue

                    # ── Init state per camera ─────────────────────────────────
                    if cam_id not in states:
                        states[cam_id] = WorkerState()
                    state = states[cam_id]
                    state.frame_ctr += 1

                    # ── Frame skip — only detect every N frames ───────────────
                    if state.frame_ctr % FRAME_SKIP != 0:
                        continue

                    # ── Resize for faster CPU inference ───────────────────────
                    h_orig, w_orig = frame.shape[:2]
                    scale = INFER_SIZE / max(h_orig, w_orig)
                    if scale < 1.0:
                        frame_inf = cv2.resize(frame, None, fx=scale, fy=scale,
                                               interpolation=cv2.INTER_LINEAR)
                    else:
                        frame_inf = frame

                    # ── YOLOv8 inference ─────────────────────────────────────
                    results = model(frame_inf, conf=CONF, verbose=False)[0]

                    ds_dets = []
                    for box in results.boxes:
                        cls = int(box.cls[0])
                        if cls not in TARGET_CLS:
                            continue
                        x1,y1,x2,y2 = box.xyxy[0].tolist()
                        # Scale bbox back to original resolution
                        if scale < 1.0:
                            x1,y1,x2,y2 = x1/scale,y1/scale,x2/scale,y2/scale
                        w_b = x2 - x1
                        h_b = y2 - y1
                        ds_dets.append(
                            ([x1, y1, w_b, h_b], float(box.conf[0]), TARGET_CLS[cls])
                        )

                    tracks = state.tracker.update_tracks(ds_dets, frame=frame)

                    for track in tracks:
                        if not track.is_confirmed():
                            continue
                        l,t,r2,b = [int(v) for v in track.to_ltrb()]
                        etype     = track.det_class or "person"
                        event = detection_event(data, etype,
                            track_id=track.track_id, conf=track.det_conf or 0,
                            x1=l, y1=t, x2=r2, y2=b,
                            frame_w=w_orig, frame_h=h_orig,
                        )
                        r.xadd(OUT_STREAM, event, maxlen=OUT_MAX, approximate=True)

                except Exception as e:
                    log.error(f"YOLO error: {e}")
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)
