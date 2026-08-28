#!/usr/bin/env python3
"""Vehicle/person detection and camera-local tracking worker."""
import os, time, base64, uuid, logging
import cv2, numpy as np
import redis
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from event_schema import detection_event

log = logging.getLogger("yolo_worker")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
CONF = float(os.getenv("DETECTION_CONF", "0.4"))
FRAME_SKIP = max(1, int(os.getenv("FRAME_SKIP", "3")))
ANPR_DISPATCH_INTERVAL = max(0.2, float(os.getenv("ANPR_DISPATCH_INTERVAL_SECS", "0.8")))
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
PREFIX = "test:" if TEST_MODE else ""
GROUP = "test_ai_workers" if TEST_MODE else "ai_workers"
IN_STREAM = f"{PREFIX}raw_frames"
RESET_STREAM = f"{PREFIX}cam_resets"
OUT_STREAM = f"{PREFIX}detections"
ANPR_STREAM = f"{PREFIX}anpr_requests"
TRACK_HASH_PREFIX = f"{PREFIX}vehicle_tracks:"
CONFIRMED_KEY_PREFIX = f"{PREFIX}anpr_confirmed:"
OUT_MAX = 5000
INFER_SIZE = int(os.getenv("INFER_SIZE", "416"))
TRACK_MAX_AGE = max(5, int(os.getenv("TRACK_MAX_AGE", "30")))
TRACK_N_INIT = max(1, int(os.getenv("TRACK_N_INIT", "3")))
TARGET_CLS = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
VEHICLE_TYPES = {"car", "motorcycle", "bus", "truck"}


def _ensure_group(r, stream, group):
    try:
        r.xgroup_create(stream, group, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass


def _decode_frame(data):
    try:
        arr = np.frombuffer(base64.b64decode(data[b"frame"]), dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _encode_crop(frame, x1, y1, x2, y2):
    h, w = frame.shape[:2]
    x1 = max(0, min(w - 1, x1)); x2 = max(x1 + 1, min(w, x2))
    y1 = max(0, min(h - 1, y1)); y2 = max(y1 + 1, min(h, y2))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    ok, encoded = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    return base64.b64encode(encoded.tobytes()).decode() if ok else None


class WorkerState:
    def __init__(self):
        self.tracker = DeepSort(max_age=TRACK_MAX_AGE, n_init=TRACK_N_INIT)
        self.frame_ctr = 0
        self.last_anpr_dispatch = {}

    def reset(self):
        self.tracker = DeepSort(max_age=TRACK_MAX_AGE, n_init=TRACK_N_INIT)
        self.frame_ctr = 0
        self.last_anpr_dispatch.clear()
        log.info("Tracker reset")


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [YOLO][%(levelname)s] %(message)s")
    log.info("Loading %s (infer_size=%s, skip=%s)", YOLO_MODEL, INFER_SIZE, FRAME_SKIP)
    model = YOLO(YOLO_MODEL)
    r = redis.from_url(REDIS_URL, decode_responses=False)
    consumer = f"yolo-{uuid.uuid4().hex[:8]}"
    _ensure_group(r, IN_STREAM, GROUP)
    _ensure_group(r, RESET_STREAM, "reset_watchers")
    _ensure_group(r, ANPR_STREAM, "anpr_probe")
    states = {}
    last_reset_id = b"0"

    while True:
        try:
            resets = r.xread({RESET_STREAM: last_reset_id}, count=20, block=1)
            for _, entries in resets or []:
                for reset_id, data in entries:
                    cam_id = data.get(b"cam_id", b"").decode()
                    if cam_id in states:
                        states[cam_id].reset()
                    last_reset_id = reset_id
            msgs = r.xreadgroup(GROUP, consumer, {IN_STREAM: ">"}, count=4, block=200)
        except redis.exceptions.ResponseError as exc:
            if "NOGROUP" in str(exc):
                _ensure_group(r, IN_STREAM, GROUP)
                continue
            raise
        if not msgs:
            continue

        for _, entries in msgs:
            for msg_id, data in entries:
                try:
                    cam_id = data.get(b"cam_id", b"").decode()
                    pts_ms = int(data.get(b"pts_ms", b"0"))
                    frame = _decode_frame(data)
                    if frame is None:
                        continue
                    state = states.setdefault(cam_id, WorkerState())
                    state.frame_ctr += 1
                    if state.frame_ctr % FRAME_SKIP:
                        continue

                    h, w = frame.shape[:2]
                    scale = INFER_SIZE / max(h, w)
                    frame_inf = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR) if scale < 1 else frame
                    results = model(frame_inf, conf=CONF, verbose=False)[0]
                    detections = []
                    for box in results.boxes:
                        cls = int(box.cls[0])
                        if cls not in TARGET_CLS:
                            continue
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        if scale < 1:
                            x1, y1, x2, y2 = x1 / scale, y1 / scale, x2 / scale, y2 / scale
                        detections.append(([x1, y1, x2 - x1, y2 - y1], float(box.conf[0]), TARGET_CLS[cls]))

                    tracks = state.tracker.update_tracks(detections, frame=frame)
                    track_key = f"{TRACK_HASH_PREFIX}{cam_id}"
                    now = time.monotonic()
                    for track in tracks:
                        if not track.is_confirmed():
                            continue
                        l, t, r2, b = [int(v) for v in track.to_ltrb()]
                        etype = track.det_class or "person"
                        track_conf = float(track.det_conf or 0.0)
                        event = detection_event(
                            data, etype, track_id=track.track_id, conf=track_conf,
                            x1=l, y1=t, x2=r2, y2=b, frame_w=w, frame_h=h,
                        )
                        r.xadd(OUT_STREAM, event, maxlen=OUT_MAX, approximate=True)

                        if etype not in VEHICLE_TYPES:
                            continue
                        cx, cy = (l + r2) // 2, (t + b) // 2
                        value = f"{l}:{t}:{r2}:{b}:{cx}:{cy}:{pts_ms}:{track_conf}:{etype}"
                        r.hset(track_key, str(track.track_id), value)
                        r.hset(track_key, f"pts:{pts_ms}:{track.track_id}", value)
                        r.expire(track_key, 10)

                        key = f"{cam_id}:{track.track_id}"
                        if r.exists(f"{CONFIRMED_KEY_PREFIX}{key}"):
                            continue
                        if now - state.last_anpr_dispatch.get(key, 0.0) < ANPR_DISPATCH_INTERVAL:
                            continue
                        crop_b64 = _encode_crop(frame, l, t, r2, b)
                        if not crop_b64:
                            continue
                        request = detection_event(
                            data, "anpr_request", track_id=track.track_id, conf=track_conf,
                            x1=l, y1=t, x2=r2, y2=b, frame_w=w, frame_h=h,
                            vehicle_type=etype, vehicle_crop=crop_b64,
                        )
                        request[b"event_type"] = b"anpr_request"
                        r.xadd(ANPR_STREAM, request, maxlen=OUT_MAX, approximate=True)
                        state.last_anpr_dispatch[key] = now
                except Exception:
                    log.error("YOLO error", exc_info=True)
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)


if __name__ == "__main__":
    run()
