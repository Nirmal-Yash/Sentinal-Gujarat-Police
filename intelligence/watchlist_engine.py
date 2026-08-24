"""Watchlist Engine — matches face embeddings and plate numbers against watchlist DB."""
import os, time, threading, logging
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger("watchlist")

DB_URL       = os.getenv("DATABASE_URL", "")
FACE_THRESH  = float(os.getenv("FACE_SIM_THRESHOLD",   "0.65"))
PLATE_THRESH = float(os.getenv("PLATE_MATCH_THRESHOLD", "0.9"))
RELOAD_SECS  = 60   # reload watchlist every minute


class WatchlistEngine:
    def __init__(self):
        self._lock      = threading.Lock()
        self._face_list = []   # list of dict: {id, name, description, priority, embedding}
        self._plates    = {}   # plate_str → dict
        self._load()
        t = threading.Thread(target=self._periodic_reload, daemon=True)
        t.start()

    # ── Public ────────────────────────────────────────────────────────────────
    def match(self, embedding=None, plate_text=None):
        """Return best watchlist hit or None."""
        with self._lock:
            # Plate match (fast exact substring)
            if plate_text:
                plate_clean = plate_text.upper().replace(" ", "")
                for stored, entry in self._plates.items():
                    if stored in plate_clean or plate_clean in stored:
                        return {**entry, "score": 1.0}

            # Face embedding match (cosine similarity)
            if embedding is not None and self._face_list:
                emb = self._norm(embedding)
                best_score = 0.0
                best_entry = None
                for entry in self._face_list:
                    sim = float(np.dot(emb, entry["embedding"]))
                    if sim > best_score:
                        best_score = sim
                        best_entry = entry
                if best_score >= FACE_THRESH and best_entry:
                    return {**best_entry, "score": best_score}

        return None

    # ── Internal ─────────────────────────────────────────────────────────────
    def _load(self):
        try:
            conn = psycopg2.connect(DB_URL)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, name, entity_type, description,
                           plate_number, alert_priority, embedding
                    FROM watchlist
                    WHERE is_active = TRUE
                """)
                rows = cur.fetchall()
            conn.close()

            faces, plates = [], {}
            for row in rows:
                entry = {
                    "id":          str(row["id"]),
                    "name":        row["name"],
                    "description": row["description"] or "",
                    "priority":    row["alert_priority"] or "HIGH",
                }
                if row["plate_number"]:
                    plates[row["plate_number"].upper().replace(" ", "")] = entry
                if row["embedding"] is not None:
                    raw = bytes(row["embedding"])
                    emb = np.frombuffer(raw, dtype=np.float32).copy()
                    entry["embedding"] = self._norm(emb)
                    faces.append(entry)

            with self._lock:
                self._face_list = faces
                self._plates    = plates

            log.info(f"Watchlist loaded: {len(faces)} faces, {len(plates)} plates")
        except Exception as e:
            log.error(f"Watchlist load error: {e}")

    def _periodic_reload(self):
        while True:
            time.sleep(RELOAD_SECS)
            self._load()

    @staticmethod
    def _norm(v):
        n = np.linalg.norm(v)
        return (v / n).astype(np.float32) if n > 1e-9 else v.astype(np.float32)
