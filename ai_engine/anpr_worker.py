#!/usr/bin/env python3
"""ANPR Worker: detect vehicles → crop plate region → EasyOCR → detections stream."""
import os, time, base64, uuid, re, logging
import cv2, numpy as np
import redis
import easyocr
from ultralytics import YOLO
from event_schema import detection_event

log = logging.getLogger("anpr_worker")

REDIS_URL  = os.getenv("REDIS_URL", "redis://localhost:6379")
CONF       = float(os.getenv("DETECTION_CONF", "0.4"))
TEST_MODE  = os.getenv("TEST_MODE", "false").lower() == "true"
PREFIX     = "test:" if TEST_MODE else ""
GROUP      = "test_anpr_workers" if TEST_MODE else "anpr_workers"
IN_STREAM  = f"{PREFIX}raw_frames"
OUT_STREAM = f"{PREFIX}detections"
TRACK_HASH_PREFIX = f"{PREFIX}vehicle_tracks:"
RESET_STREAM = f"{PREFIX}cam_resets"
OUT_MAX    = 5000
CONFIRM_FRAMES = int(os.getenv("ANPR_CONFIRM_FRAMES", "3"))
TRACK_EXPIRY_SECS = float(os.getenv("ANPR_TRACK_EXPIRY_SECS", "30"))

# Regex for Indian plates: GJxx AB 1234 or GJxxAB1234
PLATE_RE = re.compile(
    r'\b([A-Z]{2}[\s-]?\d{2}[\s-]?[A-Z]{1,3}[\s-]?\d{4})\b', re.IGNORECASE)

# Vehicle classes in COCO (car, motorcycle, bus, truck)
VEHICLE_CLS = {2, 3, 5, 7}


def preprocess_plate(crop: np.ndarray) -> np.ndarray:
    """Enhance plate crops for varied outdoor lighting conditions."""
    h, w = crop.shape[:2]
    scale = max(200 / w, 60 / h, 1.0)
    if scale > 1.0:
        crop = cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4)).apply(gray)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, 15, 8)


def _plate_candidates(frame, x1, y1, x2, y2):
    """Generate crops covering common front/rear plate positions."""
    bw, bh = x2 - x1, y2 - y1
    candidates = [
        (frame[y1 + int(bh * .65):y2, x1 + int(bw * .15):x2 - int(bw * .15)], (x1 + int(bw * .15), y1 + int(bh * .65), x2 - int(bw * .15), y2)),
        (frame[y1 + int(bh * .80):y2, x1:x2], (x1, y1 + int(bh * .80), x2, y2)),
        (frame[y1 + int(bh * .45):y1 + int(bh * .70), x1 + int(bw * .10):x2 - int(bw * .10)], (x1 + int(bw * .10), y1 + int(bh * .45), x2 - int(bw * .10), y1 + int(bh * .70))),
    ]
    return [(crop, bbox) for crop, bbox in candidates if crop.size and crop.shape[0] >= 10 and crop.shape[1] >= 20]


def _ensure_group(r):
    try:
        r.xgroup_create(IN_STREAM, GROUP, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass


def run():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [ANPR][%(levelname)s] %(message)s")
    log.info("Loading YOLO + EasyOCR …")
    model  = YOLO(os.getenv("YOLO_MODEL", "yolov8n.pt"))
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    r      = redis.from_url(REDIS_URL, decode_responses=False)
    _ensure_group(r)
    consumer = f"anpr-{uuid.uuid4().hex[:8]}"
    plate_registry = {}
    last_reset_id = b"0"
    last_expiry = time.monotonic()
    log.info("ANPR worker ready.")

    while True:
        now = time.monotonic()
        if now - last_expiry >= 10:
            for key, state in list(plate_registry.items()):
                if now - state["last_seen"] > TRACK_EXPIRY_SECS:
                    del plate_registry[key]
            last_expiry = now
        resets = r.xread({RESET_STREAM: last_reset_id}, count=20, block=1)
        for _, reset_entries in resets or []:
            for reset_id, reset_data in reset_entries:
                reset_cam = reset_data.get(b"cam_id", b"").decode()
                for key in [key for key in plate_registry if key.startswith(f"{reset_cam}:")]:
                    del plate_registry[key]
                last_reset_id = reset_id
        try:
            msgs = r.xreadgroup(GROUP, consumer, {IN_STREAM: ">"}, count=2, block=500)
        except redis.exceptions.ResponseError as exc:
            if "NOGROUP" in str(exc):
                _ensure_group(r)
                continue
            raise
        if not msgs:
            continue

        for _, entries in msgs:
            for msg_id, data in entries:
                try:
                    cam_id    = data[b"cam_id"].decode()
                    # A source wall-clock may be unavailable for RTSP.  Carry
                    # its explicit absence plus ingestion time; never invent it
                    # from PTS.
                    source_ts = data.get(b"source_ts", b"")
                    ingested_at = data.get(b"ingested_at", b"")
                    stream_id = data.get(b"stream_id", b"")
                    pts_ms = data.get(b"pts_ms", b"0")
                    buf       = base64.b64decode(data[b"frame"])
                    arr       = np.frombuffer(buf, np.uint8)
                    frame     = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is None:
                        continue

                    h, w = frame.shape[:2]
                    results = model(frame, conf=CONF, verbose=False)[0]

                    for box in results.boxes:
                        cls = int(box.cls[0])
                        if cls not in VEHICLE_CLS:
                            continue
                        x1,y1,x2,y2 = [int(v) for v in box.xyxy[0].tolist()]
                        if (x2 - x1) < 80 or (y2 - y1) < 60:
                            continue
                        # Spatially join this YOLO box with the latest DeepSORT
                        # track published by the parallel YOLO worker.
                        box_cx, box_cy = (x1 + x2) // 2, (y1 + y2) // 2
                        track_id = None
                        # ANPR and DeepSORT consume the same stream at
                        # different speeds; allow motion between their latest
                        # sampled frames while keeping the join camera-local.
                        match_limit = max(120, int(max(w, h) * 0.35))
                        target_pts = int(pts_ms or 0)
                        for tid, value in r.hgetall(f"{TRACK_HASH_PREFIX}{cam_id}").items():
                            try:
                                tid_text = tid.decode() if isinstance(tid, bytes) else str(tid)
                                parts = value.decode().split(":") if isinstance(value, bytes) else str(value).split(":")
                                if tid_text.startswith("pts:"):
                                    _, hash_pts, hash_track = tid_text.split(":", 2)
                                    if abs(int(hash_pts) - target_pts) > 1000:
                                        continue
                                    tid_text = hash_track
                                dist = abs(int(parts[0]) - box_cx) + abs(int(parts[1]) - box_cy)
                                if dist < match_limit and (track_id is None or dist < best_dist):
                                    best_dist, track_id = dist, tid_text
                            except (ValueError, IndexError):
                                continue

                        best_plate, best_ocr_conf, best_raw, best_validated = None, 0.0, "", False
                        best_bbox = (x1, y1, x2, y2)
                        for crop, crop_bbox in _plate_candidates(frame, x1, y1, x2, y2):
                            # Prefer the enhanced crop, but retain the source
                            # crop as a fallback: thresholding can erase
                            # low-contrast synthetic plates.
                            ocr_res = reader.readtext(preprocess_plate(crop), detail=1, paragraph=False)
                            if not ocr_res:
                                ocr_res = reader.readtext(crop, detail=1, paragraph=False)
                            ocr_rows = [row for row in ocr_res if isinstance(row, (list, tuple)) and len(row) >= 3]
                            if not ocr_rows:
                                continue
                            raw_text = " ".join(str(row[1]) for row in ocr_rows).upper().strip()
                            ocr_conf = max((float(row[2]) for row in ocr_rows), default=0.0)
                            candidate = re.sub(r"[^A-Z0-9]", "", raw_text)
                            match = PLATE_RE.search(raw_text)
                            if match and (not best_validated or ocr_conf > best_ocr_conf):
                                best_plate, best_ocr_conf, best_raw, best_validated = re.sub(r"[\s-]", "", match.group(1)).upper(), ocr_conf, raw_text, True
                                best_bbox = crop_bbox
                            elif not best_validated and len(candidate) >= 3 and (best_plate is None or ocr_conf > best_ocr_conf):
                                best_plate, best_ocr_conf, best_raw = candidate[:15], ocr_conf, raw_text
                                best_bbox = crop_bbox
                        # Some wide-angle/4K views place the plate outside
                        # the usual lower-third heuristic; use the complete
                        # vehicle crop as a final OCR fallback.
                        if not best_plate:
                            vehicle_crop = frame[y1:y2, x1:x2]
                            if vehicle_crop.size:
                                ocr_res = reader.readtext(vehicle_crop, detail=1, paragraph=False)
                                ocr_rows = [row for row in ocr_res if isinstance(row, (list, tuple)) and len(row) >= 3]
                                if ocr_rows:
                                    raw_text = " ".join(str(row[1]) for row in ocr_rows).upper().strip()
                                    candidate_text = re.sub(r"[^A-Z0-9]", "", raw_text)
                                    if len(candidate_text) >= 3:
                                        best_plate = candidate_text[:15]
                                        best_ocr_conf = max(float(row[2]) for row in ocr_rows)
                                        best_raw = raw_text
                        if not best_plate:
                            continue

                        detector_conf = float(box.conf[0])
                        candidate = {"plate": best_plate, "confidence": best_ocr_conf, "raw": best_raw,
                                     "validated": best_validated, "bbox": best_bbox, "detector_conf": detector_conf}
                        if track_id:
                            key = f"{cam_id}:{track_id}"
                            state = plate_registry.setdefault(key, {"frame_count": 0, "last_seen": now, "event_fired": False, "candidates": {}})
                            state["frame_count"] += 1; state["last_seen"] = now
                            observed = state["candidates"].setdefault(best_plate, {**candidate, "score": 0.0})
                            observed["score"] += best_ocr_conf
                            if best_ocr_conf > observed["confidence"]: observed.update(candidate)
                            if state["event_fired"] or state["frame_count"] < CONFIRM_FRAMES:
                                continue
                            candidate = max(state["candidates"].values(), key=lambda value: (value["score"], len(value["plate"])))
                            state["event_fired"] = True

                        plate, ocr_conf, raw_text = candidate["plate"], candidate["confidence"], candidate["raw"]
                        detector_conf = candidate["detector_conf"]
                        px1, py1, px2, py2 = candidate["bbox"]
                        combined_conf = round(detector_conf * ocr_conf, 4)
                        event = detection_event(data, "plate", raw_ocr=raw_text, plate_text=plate,
                                                ocr_conf=ocr_conf, detector_conf=detector_conf,
                                                conf=combined_conf, vehicle_type=cls,
                                                track_id=track_id or "", x1=px1, y1=py1, x2=px2, y2=py2)
                        event[b"event_type"] = b"vehicle_sighting"
                        event[b"plate_validated"] = b"1" if candidate["validated"] else b"0"
                        r.xadd(OUT_STREAM, event, maxlen=OUT_MAX, approximate=True)

                except Exception as e:
                    log.error(f"ANPR error: {e}", exc_info=True)
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)
