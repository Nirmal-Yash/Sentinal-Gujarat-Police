#!/usr/bin/env python3
"""ANPR Worker: detect vehicles → crop plate region → EasyOCR → detections stream."""
import os, time, base64, uuid, re, logging
import cv2, numpy as np
import redis
import easyocr
from ultralytics import YOLO

log = logging.getLogger("anpr_worker")

REDIS_URL  = os.getenv("REDIS_URL", "redis://localhost:6379")
CONF       = float(os.getenv("DETECTION_CONF", "0.4"))
GROUP      = "anpr_workers"
IN_STREAM  = "raw_frames"
OUT_STREAM = "detections"
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
                    timestamp = float(data[b"timestamp"])
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
                        # plate is typically bottom 25% of vehicle
                        py1 = y1 + int((y2 - y1) * 0.65)
                        py2 = y2
                        px1 = x1 + int((x2 - x1) * 0.15)
                        px2 = x2 - int((x2 - x1) * 0.15)
                        plate_crop = frame[py1:py2, px1:px2]
                        if plate_crop.size == 0:
                            continue

                        enhanced = preprocess_plate(plate_crop)
                        ocr_res  = reader.readtext(enhanced, detail=0, paragraph=True)
                        raw_text = " ".join(ocr_res).upper().strip()
                        match    = PLATE_RE.search(raw_text)
                        plate    = re.sub(r'[\s-]', '', match.group(1)).upper() \
                                   if match else raw_text[:15]

                        if len(plate) < 4:
                            continue

                        r.xadd(OUT_STREAM, {
                            b"detection_id":   str(uuid.uuid4()).encode(),
                            b"cam_id":         cam_id.encode(),
                            b"timestamp":      str(timestamp).encode(),
                            b"detection_type": b"plate",
                            b"plate_text":     plate.encode(),
                            b"conf":           str(float(box.conf[0])).encode(),
                            b"x1": str(x1).encode(), b"y1": str(y1).encode(),
                            b"x2": str(x2).encode(), b"y2": str(y2).encode(),
                        }, maxlen=OUT_MAX, approximate=True)

                except Exception as e:
                    log.error(f"ANPR error: {e}")
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)
