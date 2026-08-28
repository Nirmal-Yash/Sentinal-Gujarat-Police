"""Durable alert engine with entity-aware deduplication and Redis publication."""
import os, json, uuid, time, logging
import psycopg2

log = logging.getLogger("alert_engine")
DB_URL = os.getenv("DATABASE_URL", "")
COOLDOWN_SECS = max(1.0, float(os.getenv("ALERT_COOLDOWN", "60")))
ALERT_STREAM = "alerts"
ALERT_MAX = 10000

class AlertEngine:
    def _dedup_key(self, payload):
        details = payload.get("details") or {}
        entity = details.get("plate_text") or details.get("global_track_id") or details.get("watchlist_id") or payload.get("detection_id") or "unknown"
        return ":".join(str(v or "") for v in (payload.get("cam_id"), payload.get("alert_type"), entity))

    def fire(self, r, payload):
        key = self._dedup_key(payload)
        now = time.time()
        event_ts = payload.get("event_timestamp") or payload.get("timestamp")
        try:
            event_ts = float(event_ts) if event_ts is not None else now
        except (TypeError, ValueError):
            event_ts = now
        bucket = int(event_ts // COOLDOWN_SECS)
        dedup_key = f"{key}:{bucket}"
        alert_id = str(uuid.uuid4())
        payload["alert_id"] = alert_id
        try:
            with psycopg2.connect(DB_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO alerts
                      (id,detection_id,cam_id,alert_type,priority,confidence,entity_type,details,dedup_key,status,created_at,updated_at)
                      VALUES (%s,%s,%s::uuid,%s,%s,%s,%s,%s,%s,'NEW',to_timestamp(%s),to_timestamp(%s))
                      ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING
                      RETURNING id""",
                      (alert_id, payload.get("detection_id"), payload.get("cam_id") or None,
                       payload.get("alert_type"), payload.get("priority", "MEDIUM"), payload.get("confidence", 0.0),
                       payload.get("entity_type", "unknown"), json.dumps(payload.get("details", {})), dedup_key, event_ts, now))
                    inserted = cur.fetchone()
                    if not inserted:
                        return None
        except Exception:
            log.error("Alert persistence failed", exc_info=True)
            return None

        try:
            r.xadd(ALERT_STREAM, {
                b"schema_version": b"1.0",
                b"alert_id": alert_id.encode(),
                b"id": alert_id.encode(),
                b"event_type": b"alert",
                b"cam_id": str(payload.get("cam_id") or "").encode(),
                b"alert_type": str(payload.get("alert_type") or "").encode(),
                b"priority": str(payload.get("priority", "MEDIUM")).encode(),
                b"confidence": str(payload.get("confidence", 0.0)).encode(),
                b"entity_type": str(payload.get("entity_type", "")).encode(),
                b"details": json.dumps(payload.get("details", {})).encode(),
                b"event_timestamp": str(event_ts).encode(),
                b"alert_created_at": str(now).encode(),
                b"status": b"NEW",
            }, maxlen=ALERT_MAX, approximate=True)
        except Exception:
            log.error("Alert Redis publication failed", exc_info=True)
        return alert_id
