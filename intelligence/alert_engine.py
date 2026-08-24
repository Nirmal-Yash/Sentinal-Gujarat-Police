"""Alert Engine — deduplicates, scores, persists alerts to DB and pushes to Redis."""
import os, json, uuid, time, logging
import psycopg2
import redis as redis_lib

log = logging.getLogger("alert_engine")

DB_URL         = os.getenv("DATABASE_URL", "")
COOLDOWN_SECS  = float(os.getenv("ALERT_COOLDOWN", "60"))
ALERT_STREAM   = "alerts"
ALERT_MAX      = 10000


class AlertEngine:
    def __init__(self):
        self._recent = {}   # key → last_fired_ts  (dedup cache)

    def _dedup_key(self, payload: dict) -> str:
        return f"{payload.get('cam_id','')}-{payload.get('alert_type','')}-{payload.get('details',{}).get('watchlist_name','')}"

    def fire(self, r, payload: dict):
        key = self._dedup_key(payload)
        now = time.time()

        if now - self._recent.get(key, 0) < COOLDOWN_SECS:
            return   # suppressed

        self._recent[key] = now
        alert_id = str(uuid.uuid4())
        payload["alert_id"] = alert_id

        # Push to Redis alerts stream (consumed by API WebSocket)
        try:
            r.xadd(ALERT_STREAM, {
                b"alert_id":    alert_id.encode(),
                b"cam_id":      payload.get("cam_id", "").encode(),
                b"alert_type":  payload.get("alert_type", "").encode(),
                b"priority":    payload.get("priority", "MEDIUM").encode(),
                b"confidence":  str(payload.get("confidence", 0.0)).encode(),
                b"entity_type": payload.get("entity_type", "").encode(),
                b"details":     json.dumps(payload.get("details", {})).encode(),
                b"timestamp":   str(now).encode(),
            }, maxlen=ALERT_MAX, approximate=True)
        except Exception as e:
            log.error(f"Redis publish error: {e}")

        # Persist to PostgreSQL
        try:
            conn = psycopg2.connect(DB_URL)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO alerts
                      (id, detection_id, cam_id, alert_type, priority,
                       confidence, entity_type, details)
                    VALUES (%s, %s, %s::uuid, %s, %s, %s, %s, %s)
                """, (
                    alert_id,
                    payload.get("detection_id"),
                    payload.get("cam_id") or None,
                    payload.get("alert_type"),
                    payload.get("priority", "MEDIUM"),
                    payload.get("confidence", 0.0),
                    payload.get("entity_type", "unknown"),
                    json.dumps(payload.get("details", {})),
                ))
            conn.commit()
            conn.close()
            log.info(f"Alert fired: [{payload.get('priority')}] "
                     f"{payload.get('alert_type')} cam={payload.get('cam_id','?')[:8]}")
        except Exception as e:
            log.error(f"DB persist error: {e}")
