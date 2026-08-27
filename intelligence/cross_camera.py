"""Restart-safe cross-camera person tracker backed by Redis and PostgreSQL."""
import base64, json, os, time, threading, uuid, logging
import numpy as np
import faiss
import psycopg2
import redis

log = logging.getLogger("cross_camera")
SIM_THRESH = float(os.getenv("FACE_SIM_THRESHOLD", "0.65"))
WINDOW_SEC = float(os.getenv("CROSS_CAM_WINDOW", "300"))
DIM = 512
REBUILD_SECS = 30
STATE_KEY = "faiss:cross_camera:state:v1"


class CrossCameraTracker:
    """Rolling FAISS index. Redis restores quickly; PostgreSQL is durable fallback."""
    def __init__(self):
        self._lock = threading.Lock()
        self._embeddings = []  # (global_id, camera_id, epoch, normalized_embedding)
        self._index = None
        self._redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
        self._restore()
        threading.Thread(target=self._periodic_rebuild, daemon=True).start()

    def assign(self, cam_id: str, det_id: str, embedding: np.ndarray, ts: float) -> str:
        emb = self._norm(embedding)
        self._expire_old(ts)
        with self._lock:
            global_id = None
            if self._index is not None and self._index.ntotal:
                distances, indexes = self._index.search(emb.reshape(1, -1), k=1)
                if indexes[0][0] >= 0 and float(distances[0][0]) >= SIM_THRESH:
                    global_id = self._embeddings[indexes[0][0]][0]
            if global_id is None:
                global_id = f"GP-{uuid.uuid4().hex[:12].upper()}"
            self._embeddings.append((global_id, cam_id, ts, emb))
            self._rebuild_index()
        return global_id

    def is_new_camera(self, global_id: str, cam_id: str) -> bool:
        with self._lock:
            return any(item[0] == global_id and item[1] != cam_id for item in self._embeddings)

    @staticmethod
    def _norm(vector: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vector)
        return (vector / norm).astype(np.float32) if norm > 1e-9 else vector.astype(np.float32)

    def _restore(self):
        now = time.time()
        try:
            state = json.loads(self._redis.get(STATE_KEY) or "{}")
            entries = []
            for item in state.get("entries", []):
                if item[2] < now - WINDOW_SEC:
                    continue
                vector = np.frombuffer(base64.b64decode(item[3]), dtype=np.float32)
                if vector.size == DIM:
                    entries.append((item[0], item[1], float(item[2]), self._norm(vector)))
            if entries:
                self._embeddings = entries
                self._rebuild_index()
                log.info("Restored %s recent person embeddings from Redis", len(entries))
                return
        except Exception as exc:
            log.warning("Redis FAISS state restore failed: %s", exc)
        self._restore_from_db(now)

    def _restore_from_db(self, now: float):
        try:
            conn = psycopg2.connect(os.getenv("DATABASE_URL", ""))
            with conn.cursor() as cur:
                cur.execute("""SELECT id, last_seen_cam, EXTRACT(EPOCH FROM last_seen_at), embedding
                    FROM global_tracks WHERE entity_type='person' AND last_seen_at >= NOW() - (%s * INTERVAL '1 second')
                    AND embedding IS NOT NULL""", (WINDOW_SEC,))
                rows = cur.fetchall()
            conn.close()
            for global_id, cam_id, ts, value in rows:
                vector = np.fromstring(str(value).strip("[]"), sep=",", dtype=np.float32)
                if vector.size == DIM:
                    self._embeddings.append((global_id, str(cam_id), float(ts), self._norm(vector)))
            self._expire_old(now)
            self._rebuild_index()
            if self._embeddings:
                log.info("Rebuilt %s recent person embeddings from PostgreSQL", len(self._embeddings))
        except Exception as exc:
            log.warning("PostgreSQL FAISS fallback rebuild failed: %s", exc)

    def _snapshot(self):
        with self._lock:
            entries = [[gid, cam, ts, base64.b64encode(emb.tobytes()).decode()] for gid, cam, ts, emb in self._embeddings]
        try:
            self._redis.set(STATE_KEY, json.dumps({"version": 1, "entries": entries}), ex=max(int(WINDOW_SEC * 2), 60))
        except Exception as exc:
            log.warning("Redis FAISS state snapshot failed: %s", exc)

    def _expire_old(self, now: float):
        cutoff = now - WINDOW_SEC
        with self._lock:
            self._embeddings = [item for item in self._embeddings if item[2] >= cutoff]

    def _rebuild_index(self):
        if not self._embeddings:
            self._index = None
            return
        vectors = np.vstack([item[3] for item in self._embeddings]).astype(np.float32)
        self._index = faiss.IndexFlatIP(DIM)
        self._index.add(vectors)

    def _periodic_rebuild(self):
        while True:
            time.sleep(REBUILD_SECS)
            try:
                self._expire_old(time.time())
                with self._lock:
                    self._rebuild_index()
                self._snapshot()
            except Exception as exc:
                log.error("FAISS maintenance failed: %s", exc)
