"""Durable alert engine with entity-aware deduplication and evidence capture."""
import os
import json
import uuid
import time
import logging
import psycopg2
try:
    from .evidence_capture import capture_snapshot
except ImportError:
    from evidence_capture import capture_snapshot

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
        details = dict(payload.get("details") or {})
        snapshot_path = evidence_key = evidence_sha = None
        cam_id = payload.get("cam_id")
        if cam_id:
            try:
                captured = capture_snapshot(r, str(cam_id), alert_id, event_ts)
                if captured:
                    snapshot_path, evidence_key, evidence_sha = captured
                    details.update({"evidence_available": True, "evidence_storage_key": evidence_key, "evidence_sha256": evidence_sha})
            except Exception:
                log.error("Alert evidence capture failed", exc_info=True)
                details["evidence_available"] = False
        try:
            with psycopg2.connect(DB_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO alerts
                      (id,detection_id,cam_id,alert_type,priority,confidence,entity_type,details,dedup_key,status,created_at,updated_at)
                      VALUES (%s,%s,%s::uuid,%s,%s,%s,%s,%s,%s,'NEW',to_timestamp(%s),to_timestamp(%s))
                      ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING RETURNING id""",
                      (alert_id, payload.get("detection_id"), cam_id or None, payload.get("alert_type"), payload.get("priority", "MEDIUM"), payload.get("confidence", 0.0), payload.get("entity_type", "unknown"), json.dumps(details), dedup_key, event_ts, now))
                    if not cur.fetchone():
                        if snapshot_path:
                            try: os.unlink(snapshot_path)
                            except OSError: pass
                        return None
                    if snapshot_path:
                        cur.execute("""INSERT INTO evidence(event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata)
                            VALUES(%s,CAST(%s AS uuid),CAST(%s AS uuid),to_timestamp(%s),'image/jpeg',%s,%s,%s::jsonb)""",
                            (payload.get("detection_id") or alert_id, alert_id, cam_id, event_ts, evidence_key, evidence_sha, json.dumps({"source": "redis_snapshot", "alert_id": alert_id, "created_by": "alert_engine"})))
        except Exception:
            if snapshot_path:
                try: os.unlink(snapshot_path)
                except OSError: pass
            log.error("Alert persistence failed", exc_info=True)
            return None
        try:
            r.xadd(ALERT_STREAM, {
                b"schema_version": b"1.0", b"alert_id": alert_id.encode(), b"id": alert_id.encode(), b"event_type": b"alert",
                b"cam_id": str(cam_id or "").encode(), b"alert_type": str(payload.get("alert_type") or "").encode(),
                b"priority": str(payload.get("priority", "MEDIUM")).encode(), b"confidence": str(payload.get("confidence", 0.0)).encode(),
                b"entity_type": str(payload.get("entity_type", "")).encode(), b"details": json.dumps(details).encode(),
                b"event_timestamp": str(event_ts).encode(), b"alert_created_at": str(now).encode(), b"status": b"NEW",
            }, maxlen=ALERT_MAX, approximate=True)
        except Exception:
            log.error("Alert Redis publication failed", exc_info=True)
        return alert_id
