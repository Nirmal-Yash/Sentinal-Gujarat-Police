"""Watchlist Engine — FAISS-accelerated face matching with event-driven reload."""
import os, time, threading, logging
import numpy as np
import psycopg2
import redis
from psycopg2.extras import RealDictCursor
from sighting_store import normalize_plate

log = logging.getLogger("watchlist")
DB_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
FACE_THRESH = float(os.getenv("FACE_SIM_THRESHOLD", "0.65"))
PLATE_THRESH = float(os.getenv("PLATE_MATCH_THRESHOLD", "0.9"))
RELOAD_SECS = max(30, int(os.getenv("WATCHLIST_RELOAD_SECS", "60")))
UPDATE_CHANNEL = os.getenv("WATCHLIST_UPDATE_CHANNEL", "watchlist:updated")
EMBEDDING_DIM = 512

# ── FAISS availability ────────────────────────────────────────────────────────
# faiss-cpu==1.8.0 is already declared in requirements.txt.
# We import it once at module load; if missing, we fall back to numpy linear scan.
try:
    import faiss
    _FAISS_AVAILABLE = True
    log.info("FAISS available — O(1) face watchlist matching enabled (IndexFlatIP)")
except ImportError:
    faiss = None
    _FAISS_AVAILABLE = False
    log.warning("faiss-cpu not found — falling back to O(N) numpy face matching")


class WatchlistEngine:
    def __init__(self):
        self._lock = threading.RLock()
        self._face_list = []          # list[dict] — metadata parallel to index
        self._faiss_index = None      # faiss.IndexFlatIP, rebuilt on each _load()
        self._plates = {}
        self._generation = 0
        self._load()
        threading.Thread(target=self._update_listener, name="watchlist-events", daemon=True).start()
        threading.Thread(target=self._periodic_reload, name="watchlist-refresh", daemon=True).start()

    def match(self, embedding=None, plate_text=None):
        with self._lock:
            # ── Plate exact-match (O(1) dict lookup) ──────────────────────────
            if plate_text:
                plate_clean = normalize_plate(plate_text)
                if plate_clean:
                    entry = self._plates.get(plate_clean)
                    if entry:
                        return {**entry, "score": 1.0, "match_type": "plate", "generation": self._generation}

            # ── Face ANN match ─────────────────────────────────────────────────
            if embedding is not None and self._face_list:
                emb = self._norm(np.array(embedding, dtype=np.float32))

                if _FAISS_AVAILABLE and self._faiss_index is not None and self._faiss_index.ntotal > 0:
                    # FAISS IndexFlatIP: exact inner-product on unit-normalised vectors = cosine similarity
                    query = emb.reshape(1, EMBEDDING_DIM)
                    distances, indices = self._faiss_index.search(query, k=1)
                    best_idx = int(indices[0][0])
                    best_score = float(distances[0][0])
                    if best_idx >= 0 and best_score >= FACE_THRESH:
                        best_entry = self._face_list[best_idx]
                        return {**best_entry, "score": best_score, "match_type": "face", "generation": self._generation}
                else:
                    # Fallback: O(N) numpy linear scan
                    best_score, best_entry = 0.0, None
                    for entry in self._face_list:
                        sim = float(np.dot(emb, entry["embedding"]))
                        if sim > best_score:
                            best_score, best_entry = sim, entry
                    if best_score >= FACE_THRESH and best_entry:
                        return {**best_entry, "score": best_score, "match_type": "face", "generation": self._generation}
        return None

    def _load(self):
        try:
            conn = psycopg2.connect(DB_URL)
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT id,name,entity_type,description,plate_number,alert_priority,embedding FROM watchlist WHERE is_active=TRUE")
                    rows = cur.fetchall()
            finally:
                conn.close()

            faces, plates = [], {}
            face_vectors = []  # parallel list for FAISS index construction

            for row in rows:
                entry = {
                    "id": str(row["id"]), "name": row["name"],
                    "description": row["description"] or "", "priority": row["alert_priority"] or "HIGH",
                }
                if row["plate_number"]:
                    plate = normalize_plate(row["plate_number"])
                    if plate:
                        plates[plate] = entry
                if row["embedding"] is not None:
                    raw = bytes(row["embedding"])
                    emb = self._norm(np.frombuffer(raw, dtype=np.float32).copy())
                    entry["embedding"] = emb  # kept for fallback linear scan
                    faces.append(entry)
                    face_vectors.append(emb)

            # ── Build FAISS index ─────────────────────────────────────────────
            new_index = None
            if _FAISS_AVAILABLE and face_vectors:
                try:
                    matrix = np.stack(face_vectors, axis=0).astype(np.float32)
                    index = faiss.IndexFlatIP(EMBEDDING_DIM)
                    index.add(matrix)
                    new_index = index
                    log.info("FAISS index built: %s vectors, ntotal=%s", len(face_vectors), index.ntotal)
                except Exception:
                    log.error("FAISS index build failed; falling back to linear scan", exc_info=True)

            with self._lock:
                self._face_list = faces
                self._plates = plates
                self._faiss_index = new_index
                self._generation += 1
            log.info(
                "Watchlist loaded: %s faces, %s plates, generation=%s, faiss=%s",
                len(faces), len(plates), self._generation,
                f"ntotal={new_index.ntotal}" if new_index else "disabled",
            )
        except Exception:
            log.error("Watchlist load error", exc_info=True)

    def _update_listener(self):
        while True:
            pubsub = None
            client = None
            try:
                client = redis.from_url(REDIS_URL, decode_responses=True)
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(UPDATE_CHANNEL)
                log.info("Watchlist event listener subscribed: %s", UPDATE_CHANNEL)
                while True:
                    message = pubsub.get_message(timeout=1.0)
                    if message and message.get("type") == "message":
                        log.info("Watchlist update received: %s", message.get("data", ""))
                        self._load()
            except Exception:
                log.warning("Watchlist event listener unavailable; periodic fallback remains active", exc_info=True)
                time.sleep(3)
            finally:
                try:
                    if pubsub: pubsub.close()
                    if client: client.close()
                except Exception:
                    pass

    def _periodic_reload(self):
        while True:
            time.sleep(RELOAD_SECS)
            self._load()

    @staticmethod
    def _norm(v):
        n = np.linalg.norm(v)
        return (v / n).astype(np.float32) if n > 1e-9 else v.astype(np.float32)
