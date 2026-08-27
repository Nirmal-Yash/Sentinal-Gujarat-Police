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
OUT_MAX    = 5000

# Regex for Indian plates: GJxx AB 1234 or GJxxAB1234
PLATE_RE = re.compile(
    r'\b([A-Z]{2}[\s-]?\d{2}[\s-]?[A-Z]{1,3}[\s-]?\d{4})\b', re.IGNORECASE)

# Vehicle classes in COCO (car, motorcycle, bus, truck)
VEHICLE_CLS = {2, 3, 5, 7}


def preprocess_plate(crop):
    """Enhance plate image for better OCR."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


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
    log.info("ANPR worker ready.")

    while True:
        msgs = r.xreadgroup(GROUP, consumer, {IN_STREAM: ">"}, count=2, block=500)
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
                        # plate is typically bottom 25% of vehicle
                        py1 = y1 + int((y2 - y1) * 0.65)
                        py2 = y2
                        px1 = x1 + int((x2 - x1) * 0.15)
                        px2 = x2 - int((x2 - x1) * 0.15)
                        plate_crop = frame[py1:py2, px1:px2]
                        if plate_crop.size == 0 or plate_crop.shape[0] < 10 or plate_crop.shape[1] < 20:
                            continue

                        enhanced = preprocess_plate(plate_crop)
                        # Paragraph mode may return non-standard/short rows on
                        # some EasyOCR versions.  Parse only complete OCR rows
                        # so a malformed candidate cannot stop this worker.
                        ocr_res = reader.readtext(enhanced, detail=1, paragraph=False)
                        ocr_rows = [row for row in ocr_res if isinstance(row, (list, tuple)) and len(row) >= 3]
                        raw_text = " ".join(str(row[1]) for row in ocr_rows).upper().strip()
                        ocr_conf = max((float(row[2]) for row in ocr_rows), default=0.0)
                        match = PLATE_RE.search(raw_text)
                        if match:
                            plate = re.sub(r'[\s-]', '', match.group(1)).upper()
                            plate_validated = True
                        else:
                            # Synthetic, non-standard, or partially occluded
                            # OCR is retained as evidence but marked invalid.
                            plate = re.sub(r'[^A-Z0-9]', '', raw_text)
                            if len(plate) < 3:
                                continue
                            plate = plate[:15]
                            plate_validated = False
                        detector_conf = float(box.conf[0])
                        combined_conf = round(detector_conf * ocr_conf, 4)

                        event = detection_event(data, "plate", raw_ocr=raw_text, plate_text=plate,
                                                ocr_conf=ocr_conf, detector_conf=detector_conf,
                                                conf=combined_conf, vehicle_type=cls,
                                                x1=px1, y1=py1, x2=px2, y2=py2)
                        event[b"event_type"] = b"vehicle_sighting"
                        event[b"plate_validated"] = b"1" if plate_validated else b"0"
                        r.xadd(OUT_STREAM, event, maxlen=OUT_MAX, approximate=True)

                except Exception as e:
                    log.error(f"ANPR error: {e}", exc_info=True)
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)
