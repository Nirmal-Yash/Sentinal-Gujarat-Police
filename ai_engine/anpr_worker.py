#!/usr/bin/env python3
"""Adaptive ANPR consumer for tracked vehicle crops produced by the detector."""
import os, time, base64, uuid, logging, threading
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from queue import SimpleQueue
import cv2, numpy as np, redis, easyocr, yaml
from event_schema import detection_event
from anpr_policy import PlateObservation, TrackANPRState, normalize_indian_plate, plate_is_valid, quality_score, should_run_ocr
from shared_models import get_ocr_reader

log = logging.getLogger("anpr_worker")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
PREFIX = "test:" if TEST_MODE else ""
GROUP = "test_anpr_workers" if TEST_MODE else "anpr_workers"
IN_STREAM = f"{PREFIX}anpr_requests"
OUT_STREAM = f"{PREFIX}detections"
CONFIRMED_STREAM = f"{PREFIX}anpr_confirmed" if TEST_MODE else os.getenv("ANPR_CONFIRMED_STREAM", "sentinel:prod:anpr_confirmed")
RESET_STREAM = f"{PREFIX}cam_resets"
CONFIRMED_KEY_PREFIX = f"{PREFIX}anpr_confirmed:"
OUT_MAX = 5000
_thresholds = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "thresholds.yaml"), encoding="utf-8"))["anpr"]
TRACK_EXPIRY = max(1.0, float(os.getenv("ANPR_TRACK_EXPIRY_SECS", str(_thresholds["track_expiry_seconds"]))))
OCR_INTERVAL = max(0.2, float(os.getenv("ANPR_OCR_INTERVAL_SECS", str(_thresholds["ocr_cooldown_seconds"]))))
MIN_W = int(os.getenv("ANPR_MIN_VEHICLE_W", "80"))
MIN_H = int(os.getenv("ANPR_MIN_VEHICLE_H", "60"))
OCR_CONF = float(os.getenv("ANPR_OCR_MIN_CONF", "0.35"))
MIN_OBS = max(2, int(os.getenv("ANPR_VOTE_THRESHOLD", str(_thresholds["vote_threshold"]))))
VOTE_WINDOW_SECS = max(1.0, float(os.getenv("ANPR_VOTE_WINDOW_SECS", str(_thresholds["vote_window_seconds"]))))
TRACK_MIN_AGE = max(0.0, float(os.getenv("ANPR_TRACK_MIN_AGE_SECS", str(_thresholds["track_min_age_seconds"]))))
MAX_TRACKS = max(1, int(os.getenv("ANPR_MAX_CONCURRENT_TRACKS", "128")))
MIN_VEHICLE_W = int(os.getenv("ANPR_MIN_VEHICLE_W", "80"))
MIN_VEHICLE_H = int(os.getenv("ANPR_MIN_VEHICLE_H", "60"))
OCR_WORKERS = max(1, min(4, int(os.getenv("ANPR_OCR_WORKERS", str(_thresholds["ocr_workers"])))))
MAX_PENDING_JOBS = max(1, int(os.getenv("ANPR_MAX_PENDING_JOBS", str(_thresholds["max_pending_jobs"]))))


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
        x1, y1 = max(0, x1), max(0, y1); x2, y2 = min(w, x2), min(h, y2)
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


def _preprocess_for_ocr(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clip = float(_thresholds["preprocessing"]["clahe_clip_limit"])
    grid = int(_thresholds["preprocessing"]["clahe_grid_size"])
    gray = cv2.createCLAHE(clipLimit=clip, tileGridSize=(grid, grid)).apply(gray)
    amount = float(_thresholds["preprocessing"].get("unsharp_amount", 0.35))
    blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
    sharp = cv2.addWeighted(gray, 1.0 + amount, blur, -amount, 0)
    ok, encoded = cv2.imencode(".jpg", sharp, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return encoded.tobytes() if ok else None

def _ocr_job(image_bytes):
    reader = get_ocr_reader() or easyocr.Reader(["en"], gpu=False, verbose=False)
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None: return None
    rows = reader.readtext(image, detail=1, paragraph=False, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    best = None
    for row in rows or []:
        if isinstance(row, (list, tuple)) and len(row) >= 3:
            plate = normalize_indian_plate(str(row[1]))
            try: conf = float(row[2])
            except (TypeError, ValueError): continue
            if plate and (best is None or conf > best[1]): best = (plate, conf, str(row[1]))
    return best

def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [ANPR][%(levelname)s] %(message)s")
    gpu = os.getenv("ANPR_OCR_GPU", "false").lower() == "true"
    reader = get_ocr_reader() or easyocr.Reader(["en"], gpu=gpu, verbose=False)
    r = redis.from_url(REDIS_URL, decode_responses=False)
    _ensure_group(r)
    consumer = f"anpr-{uuid.uuid4().hex[:8]}"
    states = {}
    completed = SimpleQueue()
    pool = ProcessPoolExecutor(max_workers=OCR_WORKERS, mp_context=get_context("fork"))
    pending = 0
    pending_lock = threading.Lock()
    last_cleanup = time.monotonic()
    last_reset_id = "$"
    log.info("ANPR ready: cooldown=%ss vote=%s/%ss min_age=%ss workers=%s queue=%s gpu=%s normalization=1.1", OCR_INTERVAL, MIN_OBS, VOTE_WINDOW_SECS, TRACK_MIN_AGE, OCR_WORKERS, MAX_PENDING_JOBS, gpu)

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

        while True:
            try:
                key, meta, result = completed.get_nowait()
            except Exception:
                break
            state = states.get(key)
            if state is None or not result:
                continue
            raw_text, ocr_conf, _ = result
            normalized = normalize_indian_plate(raw_text)
            if not normalized or ocr_conf < OCR_CONF or not plate_is_valid(normalized):
                continue
            state.add(PlateObservation(normalized, ocr_conf, float(meta["track_conf"]), float(meta["quality"]), True, time.monotonic()))
            plate, consensus = state.consensus(MIN_OBS, time.monotonic())
            if not plate or state.confirmed_plate:
                continue
            state.confirmed_plate = plate
            state.confirmed_at = time.monotonic()
            state.status = "CONFIRMED"
            combined = max(0.0, min(1.0, 0.5*ocr_conf + 0.3*float(meta["track_conf"]) + 0.2*float(meta["quality"])))
            event = detection_event(meta["context"], "plate", raw_ocr=raw_text, plate_text=plate, ocr_conf=ocr_conf,
                                    detector_conf=float(meta["track_conf"]), conf=combined, vehicle_type=meta["vehicle_type"],
                                    track_id=meta["track_id"], x1=meta["x1"], y1=meta["y1"], x2=meta["x2"], y2=meta["y2"],
                                    plate_validated=1, anpr_consensus=round(consensus,4), normalization_version="1.1",
                                    vote_observations=len(state.observations))
            event[b"event_type"]=b"vehicle_sighting"
            r.xadd(OUT_STREAM,event,maxlen=OUT_MAX,approximate=True)
            r.xadd(CONFIRMED_STREAM,event,maxlen=OUT_MAX,approximate=True)
            r.setex(f"{CONFIRMED_KEY_PREFIX}{key}",int(max(5,TRACK_EXPIRY)),"1")
        try:
            resets = r.xread({RESET_STREAM: last_reset_id}, count=20, block=1)
            for _, entries in resets or []:
                for reset_id, data in entries:
                    cam = _bytes(data, "cam_id").decode()
                    affected = [k for k in states if k.startswith(cam + ":")]
                    for key in affected:
                        states.pop(key, None)
                        r.delete(f"{CONFIRMED_KEY_PREFIX}{key}")
                    last_reset_id = reset_id
            msgs = r.xreadgroup(GROUP, consumer, {IN_STREAM: ">"}, count=4, block=500)
        except redis.exceptions.ResponseError as exc:
            if "NOGROUP" in str(exc):
                _ensure_group(r); continue
            raise

        if not msgs:
            continue

        for _, entries in msgs:
            for msg_id, data in entries:
                try:
                    cam = _bytes(data, "cam_id").decode(); track_id = _bytes(data, "track_id").decode()
                    x1 = int(_bytes(data, "x1") or b"0"); y1 = int(_bytes(data, "y1") or b"0")
                    x2 = int(_bytes(data, "x2") or b"0"); y2 = int(_bytes(data, "y2") or b"0")
                    track_conf = float(_bytes(data, "conf") or b"0")
                    crop = _decode_crop(data)
                    if crop is None or crop.shape[1] < MIN_W or crop.shape[0] < MIN_H:
                        continue
                    key = f"{cam}:{track_id}"
                    state = states.setdefault(key, TrackANPRState(window_seconds=VOTE_WINDOW_SECS))
                    state.last_seen_at = now
                    first_seen = float(_bytes(data, "track_first_seen_at") or b"0")
                    if first_seen and not state.first_seen_at:
                        state.first_seen_at = first_seen
                    estimated_w = int((x2 - x1) * 0.60)
                    estimated_h = int((y2 - y1) * 0.18)
                    if state.confirmed_plate:
                        continue
                    if estimated_w < 40 or estimated_h < 12:
                        continue
                    if not should_run_ocr(state, now, OCR_INTERVAL, TRACK_MIN_AGE):
                        continue
                    candidates = [(q, c) for c in _crop_candidates(crop) if (q := _quality(c)) >= 0.20]
                    if not candidates:
                        continue
                    candidates.sort(key=lambda item: item[0], reverse=True)
                    image_bytes = _preprocess_for_ocr(candidates[0][1])
                    if not image_bytes:
                        continue
                    with pending_lock:
                        if pending >= MAX_PENDING_JOBS:
                            continue
                        pending += 1
                    state.last_ocr_at = now
                    meta={"track_conf":track_conf,"quality":candidates[0][0],"cam":cam,"track_id":track_id,
                          "x1":x1,"y1":y1,"x2":x2,"y2":y2,"vehicle_type":_bytes(data,"vehicle_type").decode() or "vehicle",
                          "context":{k:data[k] for k in (b"schema_version",b"event_id",b"cam_id",b"stream_id",b"source_ts",b"ingested_at",b"pts_ms",b"session_id") if k in data}}
                    future=pool.submit(_ocr_job,image_bytes)
                    def _done(f,key=key,meta=meta):
                        nonlocal pending
                        try: completed.put((key,meta,f.result()))
                        except Exception: completed.put((key,meta,None))
                        finally:
                            with pending_lock: pending=max(0,pending-1)
                    future.add_done_callback(_done)
                except Exception:
                    log.error("ANPR error", exc_info=True)
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)


if __name__ == "__main__":
    run()
