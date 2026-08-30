#!/usr/bin/env python3
"""On-demand person investigation and reference-photo validation worker."""
import base64, json, logging, os, uuid
from io import BytesIO

import numpy as np
import redis
from PIL import Image, ImageOps
from insightface.app import FaceAnalysis

log = logging.getLogger("person_investigation")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM = "person:investigations"
GROUP = "person_investigation_workers"
RESULT_TTL = int(os.getenv("PERSON_INVESTIGATION_RESULT_TTL", "120"))
DET_SIZE = int(os.getenv("PERSON_FACE_DET_SIZE", "640"))
DET_THRESH = float(os.getenv("PERSON_FACE_DET_THRESHOLD", "0.55"))
MAX_IMAGE_BYTES = int(os.getenv("PERSON_MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))


def ensure_group(r):
    try:
        r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass


def prepare_image(raw: bytes) -> np.ndarray:
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds configured size limit")
    with Image.open(BytesIO(raw)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode != "RGB":
            image = image.convert("RGB")
        width, height = image.size
        scale = max(1.0, 160.0 / max(1, min(width, height)))
        if scale > 1.0:
            image = image.resize((max(160, int(width * scale)), max(160, int(height * scale))), Image.Resampling.LANCZOS)
        return np.asarray(image, dtype=np.uint8)


def encode_embedding(face) -> str:
    emb = np.asarray(face.embedding, dtype=np.float32)
    emb /= np.linalg.norm(emb) + 1e-9
    return base64.b64encode(emb.tobytes()).decode()


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [PERSON][%(levelname)s] %(message)s")
    log.info("Loading on-demand InsightFace investigator …")
    app = FaceAnalysis(name="buffalo_s", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(DET_SIZE, DET_SIZE), det_thresh=DET_THRESH)
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
                operation = data.get(b"operation", b"investigate").decode()
                try:
                    raw = r.get(data[b"image_key"])
                    image = prepare_image(raw)
                    faces = app.get(image)
                    face_rows = [{
                        "x": int(face.bbox[0]), "y": int(face.bbox[1]),
                        "width": int(max(0, face.bbox[2] - face.bbox[0])),
                        "height": int(max(0, face.bbox[3] - face.bbox[1])),
                        "confidence": float(face.det_score),
                    } for face in faces]
                    if operation == "validate":
                        result = {
                            "status": "ok" if faces else "no_face",
                            "face_count": len(faces),
                            "faces": face_rows,
                            "embeddings": [],
                            "message": "Face detected" if faces else "No visible face detected",
                        }
                    else:
                        embeddings = [encode_embedding(face) for face in faces]
                        result = {
                            "status": "ok" if embeddings else "no_face",
                            "face_count": len(faces),
                            "faces": face_rows,
                            "embeddings": embeddings,
                        }
                    r.set(result_key, json.dumps(result).encode(), ex=RESULT_TTL)
                except Exception as exc:
                    log.error("Person operation %s failed: %s", request_id, exc, exc_info=True)
                    r.set(result_key, json.dumps({"status":"error","error":"Person image analysis failed","embeddings":[],"faces":[],"face_count":0}).encode(), ex=RESULT_TTL)
                finally:
                    r.xack(STREAM, GROUP, message_id)
                    if request_id:
                        r.delete(f"person:image:{request_id}")


if __name__ == "__main__":
    run()
