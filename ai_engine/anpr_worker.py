#!/usr/bin/env python3
"""Adaptive ANPR consumer for tracked vehicle crops produced by the detector."""
import os, time, base64, uuid, logging
import cv2, numpy as np, redis, easyocr
from event_schema import detection_event
from anpr_policy import PlateObservation, TrackANPRState, normalize_indian_plate, plate_is_valid, quality_score, should_run_ocr

log = logging.getLogger("anpr_worker")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
PREFIX = "test:" if TEST_MODE else ""
GROUP = "test_anpr_workers" if TEST_MODE else "anpr_workers"
IN_STREAM = f"{PREFIX}anpr_requests"
OUT_STREAM = f"{PREFIX}detections"
RESET_STREAM = f"{PREFIX}cam_resets"
CONFIRMED_KEY_PREFIX = f"{PREFIX}anpr_confirmed:"
OUT_MAX = 5000
TRACK_EXPIRY = float(os.getenv("ANPR_TRACK_EXPIRY_SECS", "30"))
OCR_INTERVAL = max(0.2, float(os.getenv("ANPR_OCR_INTERVAL_SECS", "0.8")))
MIN_W = int(os.getenv("ANPR_MIN_VEHICLE_W", "80"))
MIN_H = int(os.getenv("ANPR_MIN_VEHICLE_H", "60"))
OCR_CONF = float(os.getenv("ANPR_OCR_MIN_CONF", "0.35"))
MIN_OBS = max(2, int(os.getenv("ANPR_CONFIRM_OBSERVATIONS", "2")))
MAX_TRACKS = max(1, int(os.getenv("ANPR_MAX_CONCURRENT_TRACKS", "128")))
MIN_PLATE_W = int(os.getenv("ANPR_MIN_PLATE_WIDTH", "45"))
MIN_PLATE_H = int(os.getenv("ANPR_MIN_PLATE_HEIGHT", "15"))


def _ensure_group(r):
    try:
        r.xgroup_create(IN_STREAM, GROUP, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass


def _decode_crop(data):
    try:
        raw = base64.b64decode(data[b"vehicle_crop"])
        return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def _crop_candidates(crop):
    h, w = crop.shape[:2]
    boxes = [
        (int(w * 0.06), int(h * 0.45), int(w * 0.94), int(h * 0.98)),
        (0, int(h * 0.58), w, h),
        (int(w * 0.05), int(h * 0.25), int(w * 0.95), int(h * 0.80)),
    ]
    out = []
    for x1, y1, x2, y2 in boxes:
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        candidate = crop[y1:y2, x1:x2]
        if candidate.size and candidate.shape[1] >= MIN_PLATE_W and candidate.shape[0] >= MIN_PLATE_H:
            out.append(candidate)
    return out


def _quality(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blur = min(1.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 500.0)
    return quality_score(crop.shape[1], crop.shape[0], blur, float(gray.mean()) / 255.0)


def _ocr(reader, crop):
    h, w = crop.shape[:2]
    scale = max(2.0, min(4.0, 260.0 / max(1, w)))
    upscaled = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
    variants = [upscaled, cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4)).apply(gray)]
    best = None
    for image in variants:
        try:
            rows = reader.readtext(image, detail=1, paragraph=False, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        except Exception:
            log.error("OCR provider error", exc_info=True)
            continue
        for row in rows or []:
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue
            text = normalize_indian_plate(str(row[1]))
            try:
                conf = float(row[2])
            except (TypeError, ValueError):
                continue
            if text and (best is None or conf > best[1]):
                best = (text, conf)
    return best


def _bytes(data, key):
    return data.get(key.encode(), b"")


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [ANPR][%(levelname)s] %(message)s")
    gpu = os.getenv("ANPR_OCR_GPU", "false").lower() == "true"
    reader = easyocr.Reader(["en"], gpu=gpu, verbose=False)
    r = redis.from_url(REDIS_URL, decode_responses=False)
    _ensure_group(r)
    consumer = f"anpr-{uuid.uuid4().hex[:8]}"
    states = {}
    last_cleanup = time.monotonic()
    # Only consume reset messages generated after this worker starts. Historical
    # resets cannot invalidate freshly initialized state and replaying them on
    # every loop would repeatedly clear active OCR state.
    last_reset_id = "$"
    log.info("ANPR ready: track-driven requests interval=%ss gpu=%s", OCR_INTERVAL, gpu)

    while True:
        now = time.monotonic()
        if now - last_cleanup >= 5:
            for key in [k for k, state in states.items() if now - state.last_seen_at > TRACK_EXPIRY]:
                states.pop(key, None)
            if len(states) > MAX_TRACKS:
                old = sorted(states, key=lambda k: states[k].last_seen_at)[:len(states) - MAX_TRACKS]
                for key in old:
                    states.pop(key, None)
            last_cleanup = now

        try:
            resets = r.xread({RESET_STREAM: last_reset_id}, count=20, block=1)
            for _, entries in resets or []:
                for reset_id, data in entries:
                    cam = _bytes(data, "cam_id").decode()
                    for key in [k for k in states if k.startswith(cam + ":")]:
                        states.pop(key, None)
                    for key in [f"{CONFIRMED_KEY_PREFIX}{k}" for k in list(states) if k.startswith(cam + ":")]:
                        r.delete(key)
                    last_reset_id = reset_id
            msgs = r.xreadgroup(GROUP, consumer, {IN_STREAM: ">"}, count=4, block=500)
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
                    cam = _bytes(data, "cam_id").decode()
                    track_id = _bytes(data, "track_id").decode()
                    x1 = int(_bytes(data, "x1") or b"0")
                    y1 = int(_bytes(data, "y1") or b"0")
                    x2 = int(_bytes(data, "x2") or b"0")
                    y2 = int(_bytes(data, "y2") or b"0")
                    track_conf = float(_bytes(data, "conf") or b"0")
                    crop = _decode_crop(data)
                    if crop is None or crop.shape[1] < MIN_W or crop.shape[0] < MIN_H:
                        continue
                    key = f"{cam}:{track_id}"
                    state = states.setdefault(key, TrackANPRState())
                    state.last_seen_at = now
                    if not should_run_ocr(state, now, OCR_INTERVAL):
                        continue
                    best = None
                    for candidate in _crop_candidates(crop):
                        q = _quality(candidate)
                        if q < 0.20:
                            continue
                        found = _ocr(reader, candidate)
                        if found and (best is None or found[1] > best[1]):
                            best = (found[0], found[1], q)
                    state.last_ocr_at = now
                    if not best:
                        continue
                    text, ocr_conf, q = best
                    normalized = normalize_indian_plate(text)
                    if not normalized or ocr_conf < OCR_CONF or not plate_is_valid(normalized):
                        continue
                    state.add(PlateObservation(normalized, ocr_conf, track_conf, q, True, now))
                    state.status = "CONFIRMING"
                    plate, consensus = state.consensus(MIN_OBS)
                    if not plate or state.confirmed_plate:
                        continue
                    state.confirmed_plate = plate
                    state.confirmed_at = now
                    state.status = "CONFIRMED"
                    combined = max(0.0, min(1.0, 0.5 * ocr_conf + 0.3 * track_conf + 0.2 * q))
                    context = {k: data[k] for k in (b"schema_version", b"event_id", b"cam_id", b"stream_id", b"source_ts", b"ingested_at", b"pts_ms", b"session_id") if k in data}
                    event = detection_event(
                        context, "plate", raw_ocr=text, plate_text=plate, ocr_conf=ocr_conf,
                        detector_conf=track_conf, conf=combined,
                        vehicle_type=_bytes(data, "vehicle_type").decode() or "vehicle",
                        track_id=track_id, x1=x1, y1=y1, x2=x2, y2=y2,
                        plate_validated=1, anpr_consensus=round(consensus, 4),
                    )
                    event[b"event_type"] = b"vehicle_sighting"
                    r.xadd(OUT_STREAM, event, maxlen=OUT_MAX, approximate=True)
                    r.setex(f"{CONFIRMED_KEY_PREFIX}{key}", int(max(5, TRACK_EXPIRY)), "1")
                    log.info("Confirmed plate=%s camera=%s track=%s confidence=%.3f", plate, cam, track_id, combined)
                except Exception:
                    log.error("ANPR error", exc_info=True)
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)


if __name__ == "__main__":
    run()
