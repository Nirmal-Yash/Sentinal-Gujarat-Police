#!/usr/bin/env python3
"""On-demand person investigation embedding worker.

Uses the same InsightFace model as live face analytics, but only runs when an
investigator explicitly submits a reference image. Results are short-lived in
Redis and never enter the live detection stream.
"""
import base64, json, logging, os, uuid
import cv2
import numpy as np
import redis
from insightface.app import FaceAnalysis

log = logging.getLogger("person_investigation")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM = "person:investigations"
GROUP = "person_investigation_workers"
RESULT_TTL = int(os.getenv("PERSON_INVESTIGATION_RESULT_TTL", "120"))


def ensure_group(r):
    try:
        r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [PERSON][%(levelname)s] %(message)s")
    log.info("Loading on-demand InsightFace investigator …")
    app = FaceAnalysis(name="buffalo_s", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(320, 320))
    r = redis.from_url(REDIS_URL, decode_responses=False)
    ensure_group(r)
    consumer = f"person-{uuid.uuid4().hex[:8]}"
    log.info("Person investigation worker ready.")
    while True:
        try:
            messages = r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=1, block=1000)
        except redis.exceptions.ResponseError as exc:
            if "NOGROUP" in str(exc):
                ensure_group(r)
                continue
            raise
        if not messages:
            continue
        for _, entries in messages:
            for message_id, data in entries:
                request_id = data.get(b"request_id", b"").decode()
                result_key = data.get(b"result_key", f"person:result:{request_id}".encode()).decode()
                try:
                    raw = r.get(data[b"image_key"])
                    if not raw:
                        raise ValueError("reference image expired")
                    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if image is None:
                        raise ValueError("reference image could not be decoded")
                    faces = app.get(image)
                    detections = []
                    embeddings = []
                    for face in faces:
                        emb = face.embedding.astype(np.float32)
                        emb /= np.linalg.norm(emb) + 1e-9
                        embeddings.append(base64.b64encode(emb.tobytes()).decode())
                        x1, y1, x2, y2 = [int(v) for v in face.bbox.tolist()]
                        detections.append({
                            "x": x1,
                            "y": y1,
                            "width": max(0, x2 - x1),
                            "height": max(0, y2 - y1),
                            "confidence": float(face.det_score),
                        })
                    result = {
                        "status": "ok" if detections else "no_face",
                        "embeddings": embeddings,
                        "face_count": len(detections),
                        "faces": detections,
                    }
                    r.set(result_key, json.dumps(result).encode(), ex=RESULT_TTL)
                except Exception as exc:
                    log.error("Investigation %s failed: %s", request_id, exc, exc_info=True)
                    r.set(result_key, json.dumps({"status": "error", "error": "Person analysis failed", "embeddings": [], "face_count": 0, "faces": []}).encode(), ex=RESULT_TTL)
                finally:
                    r.xack(STREAM, GROUP, message_id)
                    if request_id:
                        r.delete(f"person:image:{request_id}")


if __name__ == "__main__":
    run()
