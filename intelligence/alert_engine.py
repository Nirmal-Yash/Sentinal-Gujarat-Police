"""Durable alert engine with Redis-first deduplication and durable DB uniqueness."""
import os, json, uuid, time, hashlib, logging
import psycopg2
try:
    from .plate_normalise import normalize_plate
except ImportError:
    from plate_normalise import normalize_plate
try:
    from .evidence_capture import capture_snapshot_bundle, build_human_summary
except ImportError:
    from evidence_capture import capture_snapshot_bundle, build_human_summary

log = logging.getLogger("alert_engine")
DB_URL = os.getenv("DATABASE_URL", "")
COOLDOWN_SECS = max(1.0, float(os.getenv("ALERT_COOLDOWN", "60")))
PLATE_DEDUP_WINDOW_SECS = max(60, int(os.getenv("PLATE_DEDUP_WINDOW_SECS", "1800")))
REDIS_DEDUP_PREFIX = os.getenv("ALERT_DEDUP_PREFIX", "sentinel:alert:dedup:")
ALERT_STREAM = "alerts"
ALERT_EVENT_STREAM = os.getenv("ALERT_EVENT_STREAM", "sentinel:prod:alert_events")
ALERT_MAX = 10000


def _alert_detections(payload, details):
    values = payload.get("detections") or details.get("detections")
    if isinstance(values, list):
        return values
    bbox = details.get("bbox") or payload.get("bbox")
    if bbox:
        return [{"bbox": bbox, "label": details.get("detection_type") or payload.get("entity_type"), "plate_text": details.get("plate_text")}]
    return []


class AlertEngine:
    @staticmethod
    def _canonical_type(value):
        raw = str(value or "").lower()
        if raw in {"watchlist_match", "watchlist_hit"}: return "WATCHLIST_HIT"
        if raw in {"cross_camera_sighting", "person_match", "face_match"}: return "PERSON_MATCH"
        if raw in {"plate_sighting", "plate_detected", "test_plate_detected"}: return "PLATE_SIGHTING"
        if raw in {"running_crowd", "anomaly_running_crowd"}: return "RUNNING_CROWD"
        if raw in {"crowd_anomaly", "crowd_formation", "anomaly_crowd_formation"}: return "CROWD_ANOMALY"
        if raw.startswith("anomaly_"):
            return "RUNNING_CROWD" if "running" in raw else "CROWD_ANOMALY"
        return str(value or "UNKNOWN_ALERT").upper()

    @staticmethod
    def _priority(alert_type, value):
        canonical = AlertEngine._canonical_type(alert_type)
        if canonical in {"WATCHLIST_HIT", "RUNNING_CROWD"}: return "CRITICAL"
        return str(value or ("HIGH" if canonical in {"PLATE_SIGHTING", "CROWD_ANOMALY", "PERSON_MATCH"} else "MEDIUM")).upper()

    @staticmethod
    def _dedup_key(payload):
        details = payload.get("details") or {}
        alert_type = AlertEngine._canonical_type(payload.get("alert_type"))
        cam_id = str(payload.get("cam_id") or "")
        normalized_plate = normalize_plate(details.get("normalized_plate") or details.get("plate_text")) or ""
        watchlist_id = details.get("watchlist_id")
        global_track_id = details.get("global_track_id")
        if alert_type in {"CROWD_ANOMALY", "RUNNING_CROWD"}:
            entity = f"camera:{cam_id}"
        elif normalized_plate:
            entity = f"plate:{normalized_plate}"
        elif watchlist_id:
            entity = f"watchlist:{watchlist_id}"
        elif global_track_id:
            entity = f"track:{global_track_id}"
        else:
            entity = f"detection:{payload.get('detection_id') or 'unknown'}"
        return f"{cam_id}:{alert_type}:{entity}"

    @staticmethod
    def _redis_claim(r, raw_key, ttl):
        redis_key = raw_key if str(raw_key).startswith("sentinel:dedup:") else REDIS_DEDUP_PREFIX + hashlib.sha256(raw_key.encode()).hexdigest()
        try:
            claimed = r.set(redis_key, str(time.time()), nx=True, ex=max(1, int(ttl)))
            return bool(claimed), redis_key
        except Exception:
            log.warning("Redis dedup unavailable; falling back to database uniqueness", exc_info=True)
            return True, None

    def fire(self, r, payload):
        key = self._dedup_key(payload)
        now = time.time()
        event_ts = payload.get("event_timestamp") or payload.get("timestamp")
        try: event_ts = float(event_ts) if event_ts is not None else now
        except (TypeError, ValueError): event_ts = now
        alert_type = self._canonical_type(payload.get("alert_type"))
        details = dict(payload.get("details") or {})
        normalized_plate = normalize_plate(details.get("normalized_plate") or details.get("plate_text")) or ""
        if normalized_plate and alert_type in {"WATCHLIST_HIT", "PLATE_SIGHTING"}:
            bucket = int(event_ts // PLATE_DEDUP_WINDOW_SECS)
            dedup_key = f"sentinel:dedup:plate:{payload.get('cam_id') or ''}:{normalized_plate}:{bucket}"
            dedup_ttl = PLATE_DEDUP_WINDOW_SECS
        else:
            bucket = int(event_ts // COOLDOWN_SECS)
            dedup_key = f"{key}:{bucket}"
            dedup_ttl = COOLDOWN_SECS
        claimed, redis_key = self._redis_claim(r, dedup_key, dedup_ttl)
        if not claimed: return None
        alert_id = str(uuid.uuid4())
        payload["alert_type"] = alert_type
        payload["priority"] = self._priority(alert_type, payload.get("priority"))
        details.setdefault("dedup_key", key); details.setdefault("dedup_bucket", bucket)
        snapshot_path = thumbnail_path = evidence_key = thumbnail_key = evidence_sha = None
        cam_id = payload.get("cam_id")
        camera_name = payload.get("camera_name") or cam_id or "Camera"
        details["human_summary"] = details.get("human_summary") or build_human_summary(payload.get("alert_type"), details, camera_name)
        details.setdefault("message", details["human_summary"])
        details["detection_detail"] = details.get("detection_detail") or {k: v for k, v in details.items() if k not in {"dedup_key", "dedup_bucket", "detections"}}
        details["evidence"] = {"available": False, "description": "Evidence frame unavailable."}
        if cam_id:
            try:
                captured = capture_snapshot_bundle(r, str(cam_id), alert_id, event_ts, detections=_alert_detections(payload, details), alert_type=payload.get("alert_type"), camera_name=camera_name)
                if captured:
                    snapshot_path, thumbnail_path = captured["stored_path"], captured["thumbnail_path"]
                    evidence_key, thumbnail_key, evidence_sha = captured["storage_key"], captured["thumbnail_key"], captured["sha256"]
            except Exception:
                log.error("Alert evidence capture failed", exc_info=True)
        try:
            with psycopg2.connect(DB_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO alerts
                      (id,detection_id,cam_id,alert_type,priority,confidence,entity_type,details,dedup_key,status,created_at,updated_at)
                      VALUES (%s,%s,%s::uuid,%s,%s,%s,%s,%s,%s,'NEW',to_timestamp(%s),to_timestamp(%s))
                      ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING RETURNING id""",
                      (alert_id, payload.get("detection_id"), cam_id or None, payload.get("alert_type"), payload.get("priority", "MEDIUM"), payload.get("confidence", 0.0), payload.get("entity_type", "unknown"), json.dumps(details), dedup_key, event_ts, now))
                    inserted = cur.fetchone()
                    if not inserted:
                        if snapshot_path:
                            try: os.unlink(snapshot_path)
                            except OSError: pass
                        if thumbnail_path:
                            try: os.unlink(thumbnail_path)
                            except OSError: pass
                        return None
                    if snapshot_path:
                        cur.execute("""INSERT INTO evidence(event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata)
                            VALUES(%s,CAST(%s AS uuid),CAST(%s AS uuid),to_timestamp(%s),'image/jpeg',%s,%s,%s::jsonb) RETURNING id""",
                            (payload.get("detection_id") or alert_id, alert_id, cam_id, event_ts, evidence_key, evidence_sha, json.dumps({"source": "redis_snapshot", "alert_id": alert_id, "created_by": "alert_engine", "thumbnail_key": thumbnail_key, "frame_width": captured.get("frame_width"), "frame_height": captured.get("frame_height"), "detections_count": captured.get("detections_count")})))
                        evidence_id = str(cur.fetchone()[0])
                        details["evidence"] = {"available": True, "evidence_id": evidence_id, "frame_url": f"/api/evidence/{evidence_id}/content", "thumbnail_url": f"/api/evidence/{evidence_id}/thumbnail", "description": captured.get("description")}
                        cur.execute("UPDATE alerts SET details=%s::jsonb WHERE id=%s", (json.dumps(details), alert_id))
        except Exception:
            if snapshot_path:
                try: os.unlink(snapshot_path)
                except OSError: pass
            if thumbnail_path:
                try: os.unlink(thumbnail_path)
                except OSError: pass
            if redis_key:
                try: r.delete(redis_key)
                except Exception: pass
            log.error("Alert persistence failed", exc_info=True); return None
        try:
            event_payload = {
                b"schema_version": b"1.0", b"alert_id": alert_id.encode(), b"id": alert_id.encode(), b"event_type": b"alert",
                b"cam_id": str(cam_id or "").encode(), b"alert_type": str(payload.get("alert_type") or "").encode(),
                b"priority": str(payload.get("priority", "MEDIUM")).encode(), b"confidence": str(payload.get("confidence", 0.0)).encode(),
                b"entity_type": str(payload.get("entity_type", "")).encode(), b"details": json.dumps(details).encode(),
                b"event_timestamp": str(event_ts).encode(), b"alert_created_at": str(now).encode(), b"status": b"NEW",
            }
            r.xadd(ALERT_STREAM, event_payload, maxlen=ALERT_MAX, approximate=True)
            if ALERT_EVENT_STREAM != ALERT_STREAM:
                r.xadd(ALERT_EVENT_STREAM, event_payload, maxlen=ALERT_MAX, approximate=True)
        except Exception:
            log.error("Alert Redis publication failed", exc_info=True)
        return alert_id
