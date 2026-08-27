#!/usr/bin/env python3
"""Face Worker: detect persons → crop face → InsightFace ArcFace 512-d embedding."""
import os, base64, uuid, logging
import cv2, numpy as np
import redis
from ultralytics import YOLO
import insightface
from insightface.app import FaceAnalysis
from event_schema import detection_event

log = logging.getLogger("face_worker")

REDIS_URL  = os.getenv("REDIS_URL", "redis://localhost:6379")
CONF       = float(os.getenv("DETECTION_CONF", "0.4"))
TEST_MODE  = os.getenv("TEST_MODE", "false").lower() == "true"
PREFIX     = "test:" if TEST_MODE else ""
GROUP      = "test_face_workers" if TEST_MODE else "face_workers"
IN_STREAM  = f"{PREFIX}raw_frames"
OUT_STREAM = f"{PREFIX}detections"
OUT_MAX    = 5000

PERSON_CLS = {0}   # COCO class 0 = person


def _ensure_group(r):
    try:
        r.xgroup_create(IN_STREAM, GROUP, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass


def run():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [FACE][%(levelname)s] %(message)s")
    log.info("Loading YOLO + InsightFace ArcFace …")
    yolo = YOLO(os.getenv("YOLO_MODEL", "yolov8n.pt"))

    face_app = FaceAnalysis(
        name="buffalo_s",          # lightweight model
        providers=["CPUExecutionProvider"],
    )
    face_app.prepare(ctx_id=0, det_size=(320, 320))

    r        = redis.from_url(REDIS_URL, decode_responses=False)
    _ensure_group(r)
    consumer = f"face-{uuid.uuid4().hex[:8]}"
    log.info("Face worker ready.")

    while True:
        msgs = r.xreadgroup(GROUP, consumer, {IN_STREAM: ">"}, count=2, block=500)
        if not msgs:
            continue

        for _, entries in msgs:
            for msg_id, data in entries:
                try:
                    cam_id    = data[b"cam_id"].decode()
                    buf       = base64.b64decode(data[b"frame"])
                    arr       = np.frombuffer(buf, np.uint8)
                    frame     = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is None:
                        continue

                    # Detect persons first (faster than full face scan on whole frame)
                    results = yolo(frame, conf=CONF, classes=[0], verbose=False)[0]
                    for box in results.boxes:
                        x1,y1,x2,y2 = [int(v) for v in box.xyxy[0].tolist()]
                        # add head room above bounding box
                        head_h = max(0, y1 - int((y2 - y1) * 0.15))
                        crop   = frame[head_h:y2, x1:x2]
                        if crop.size == 0:
                            continue

                        faces = face_app.get(crop)
                        for face in faces:
                            emb = face.embedding          # shape (512,)
                            emb_norm = emb / (np.linalg.norm(emb) + 1e-9)
                            emb_b64  = base64.b64encode(
                                emb_norm.astype(np.float32).tobytes()
                            ).decode()

                            r.xadd(OUT_STREAM, detection_event(
                                data, "face", embedding=emb_b64, conf=float(face.det_score),
                                x1=x1, y1=y1, x2=x2, y2=y2), maxlen=OUT_MAX, approximate=True)

                except Exception as e:
                    log.error(f"Face error: {e}")
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)
