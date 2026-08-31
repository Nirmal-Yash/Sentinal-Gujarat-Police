"""Watchlist Engine — event-driven reload with periodic safety fallback."""
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


class WatchlistEngine:
    def __init__(self):
        self._lock = threading.RLock()
        self._face_list = []
        self._plates = {}
        self._generation = 0
        self._load()
        threading.Thread(target=self._update_listener, name="watchlist-events", daemon=True).start()
        threading.Thread(target=self._periodic_reload, name="watchlist-refresh", daemon=True).start()

    def match(self, embedding=None, plate_text=None):
        with self._lock:
            if plate_text:
                plate_clean = normalize_plate(plate_text)
                if plate_clean:
                    entry = self._plates.get(plate_clean)
                    if entry:
                        return {**entry, "score": 1.0, "match_type": "plate", "generation": self._generation}
            if embedding is not None and self._face_list:
                emb = self._norm(embedding)
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
                    entry["embedding"] = emb
                    faces.append(entry)
            with self._lock:
                self._face_list, self._plates = faces, plates
                self._generation += 1
            log.info("Watchlist loaded: %s faces, %s plates, generation=%s", len(faces), len(plates), self._generation)
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
