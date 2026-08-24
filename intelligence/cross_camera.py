"""Cross-camera entity tracker using FAISS approximate nearest neighbour search."""
import os, uuid, time, threading, logging
import numpy as np
import faiss

log = logging.getLogger("cross_camera")

SIM_THRESH   = float(os.getenv("FACE_SIM_THRESHOLD", "0.65"))
WINDOW_SEC   = float(os.getenv("CROSS_CAM_WINDOW", "300"))   # 5 min
DIM          = 512
REBUILD_SECS = 30   # rebuild FAISS index every N seconds


class CrossCameraTracker:
    """
    Maintains a rolling FAISS index of recent face embeddings.
    Assigns global_track_id across camera boundaries.
    """

    def __init__(self):
        self._lock       = threading.Lock()
        self._embeddings = []   # list of (global_id, cam_id, ts, ndarray)
        self._index      = None
        self._rebuild()
        t = threading.Thread(target=self._periodic_rebuild, daemon=True)
        t.start()

    # ── Public API ────────────────────────────────────────────────────────────
    def assign(self, cam_id: str, det_id: str, embedding: np.ndarray,
               ts: float) -> str:
        """
        Find nearest existing embedding. If within threshold → reuse global_id.
        Otherwise create new one.
        """
        emb = self._norm(embedding)
        self._expire_old(ts)

        global_id = None
        with self._lock:
            if self._index is not None and self._index.ntotal > 0:
                D, I = self._index.search(emb.reshape(1, -1), k=1)
                if len(I) > 0 and I[0][0] >= 0:
                    sim = float(D[0][0])
                    if sim >= SIM_THRESH:
                        global_id = self._embeddings[I[0][0]][0]

            if global_id is None:
                global_id = f"GT-{uuid.uuid4().hex[:12].upper()}"

            self._embeddings.append((global_id, cam_id, ts, emb))
            self._rebuild_index()

        return global_id

    def is_new_camera(self, global_id: str, cam_id: str) -> bool:
        """Return True if this global_id has been seen on a different camera before."""
        with self._lock:
            past_cams = {e[1] for e in self._embeddings
                         if e[0] == global_id and e[1] != cam_id}
        return bool(past_cams)

    # ── Internal ─────────────────────────────────────────────────────────────
    @staticmethod
    def _norm(v: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(v)
        return (v / n).astype(np.float32) if n > 1e-9 else v.astype(np.float32)

    def _expire_old(self, now: float):
        cutoff = now - WINDOW_SEC
        with self._lock:
            self._embeddings = [e for e in self._embeddings if e[2] >= cutoff]

    def _rebuild_index(self):
        """Rebuild flat cosine index (call inside lock)."""
        if not self._embeddings:
            self._index = None
            return
        vecs = np.vstack([e[3] for e in self._embeddings]).astype(np.float32)
        index = faiss.IndexFlatIP(DIM)   # Inner product = cosine on unit vecs
        index.add(vecs)
        self._index = index

    def _rebuild(self):
        with self._lock:
            self._rebuild_index()

    def _periodic_rebuild(self):
        while True:
            time.sleep(REBUILD_SECS)
            try:
                self._expire_old(time.time())
                with self._lock:
                    self._rebuild_index()
                log.debug(f"FAISS index rebuilt — {len(self._embeddings)} entries")
            except Exception as e:
                log.error(f"FAISS rebuild error: {e}")
