"""Persistence boundary and regression tests for isolated test mode."""
import base64, json, os, unittest
from datetime import datetime, timezone
import psycopg2
from plate_normalise import normalize_plate

DB_URL = os.getenv("DATABASE_URL", "")
ALERT_COOLDOWN = max(1, int(os.getenv("ALERT_COOLDOWN", "60")))


def _value(data, name, default=""):
    value = data.get(name.encode(), default.encode() if isinstance(default, str) else default)
    return value.decode() if isinstance(value, bytes) else str(value)


def _timestamp(data):
    try:
        value = _value(data, "source_ts") or _value(data, "ingested_at")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _truthy(data, name):
    return _value(data, name).strip().lower() in {"1", "true", "yes"}


def _vector_literal(encoded):
    raw = base64.b64decode(encoded)
    import numpy as np
    values = np.frombuffer(raw, dtype=np.float32)
    if values.size != 512:
        raise ValueError("test face embedding must contain 512 float32 values")
    values = values / (np.linalg.norm(values) + 1e-9)
    return "[" + ",".join(str(float(v)) for v in values) + "]"


def persist(data: dict):
    """Store test analytics and create an alert only for a real watchlist hit."""
    session_id, detection_id = _value(data, "session_id"), _value(data, "detection_id") or _value(data, "event_id")
    if not session_id or not detection_id:
        raise ValueError("test event is missing session_id or detection_id")
    timestamp = _timestamp(data)
    stream_id = int(_value(data, "stream_id", "0") or 0)
    kind = _value(data, "detection_type", "unknown")
    camera_label = f"Test Camera {stream_id}"
    track_id = _value(data, "track_id") or None
    plate = normalize_plate(_value(data, "plate_text"))
    confidence = max(0.0, min(1.0, float(_value(data, "conf", "0") or 0)))
    bbox = {key: _value(data, key) for key in ("x1","y1","x2","y2") if key.encode() in data}
    details = {
        "schema_version": _value(data, "schema_version", "1.0"), "event_id": _value(data, "event_id", detection_id),
        "raw_ocr": _value(data, "raw_ocr", ""), "pts_ms": _value(data, "pts_ms", "0"),
        "plate_validated": _value(data, "plate_validated", ""), "anpr_consensus": _value(data, "anpr_consensus", ""),
        "track_id": track_id,
    }
    global_track = f"test:{stream_id}:{kind}:{track_id or detection_id}"
    embedding = _value(data, "embedding") or None
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT camera_label FROM test_session_feeds WHERE session_id=%s::uuid AND stream_id=%s", (session_id, stream_id))
            camera_label = (cur.fetchone() or [camera_label])[0]
            cur.execute("""INSERT INTO test_detections(id,session_id,camera_label,detection_type,plate_text,confidence,event_at,source_timestamp,stream_id,track_id,bbox,details)
              VALUES(%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT(id) DO NOTHING""",
              (detection_id,session_id,camera_label,kind,plate,confidence,timestamp,timestamp,stream_id,track_id,json.dumps(bbox),json.dumps(details)))
            cur.execute("""INSERT INTO test_tracks(session_id,global_track_id,entity_type,first_camera_label,last_camera_label,first_seen_at,last_seen_at,sightings)
              VALUES(%s::uuid,%s,%s,%s,%s,%s,%s,jsonb_build_array(jsonb_build_object('camera_label',%s,'timestamp',%s)))
              ON CONFLICT(session_id,global_track_id) DO UPDATE SET last_camera_label=EXCLUDED.last_camera_label,last_seen_at=EXCLUDED.last_seen_at,sightings=test_tracks.sightings || EXCLUDED.sightings""",
              (session_id,global_track,camera_label,camera_label,timestamp,timestamp,camera_label,timestamp.isoformat()))
            if embedding and kind == "face":
                cur.execute("UPDATE test_tracks SET embedding=CAST(%s AS vector) WHERE session_id=%s::uuid AND global_track_id=%s", (_vector_literal(embedding), session_id, global_track))
            alert = None; watchlist_match = None
            if kind == "plate" and plate and _truthy(data, "plate_validated") and _truthy(data, "anpr_consensus"):
                cur.execute("""SELECT id,name,description,alert_priority FROM watchlist
                    WHERE is_active=TRUE AND plate_number IS NOT NULL
                    AND regexp_replace(upper(plate_number),'[^A-Z0-9]','','g')=%s LIMIT 1""", (plate,))
                watchlist_match = cur.fetchone()
                if watchlist_match:
                    wl_id, wl_name, wl_description, wl_priority = watchlist_match
                    cur.execute("""SELECT id FROM test_alerts
                        WHERE session_id=%s::uuid AND alert_type='watchlist_match' AND details->>'watchlist_id'=%s
                          AND COALESCE(details->>'track_id','')=COALESCE(%s,'')
                          AND event_at >= %s - (%s * INTERVAL '1 second') ORDER BY event_at DESC LIMIT 1""",
                        (session_id,str(wl_id),track_id,timestamp,ALERT_COOLDOWN))
                    existing = cur.fetchone()
                    if not existing:
                        cur.execute("""INSERT INTO test_alerts(session_id,detection_id,alert_type,priority,event_at,details)
                          VALUES(%s::uuid,%s::uuid,'watchlist_match',%s,%s,%s::jsonb) RETURNING id""",
                          (session_id,detection_id,wl_priority or 'HIGH',timestamp,json.dumps({"plate_text":plate,"camera_label":camera_label,"watchlist_id":str(wl_id),"watchlist_name":wl_name,"description":wl_description or "","track_id":track_id,"test":True})))
                        alert = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return {"session_id":session_id,"detection_id":detection_id,"camera_label":camera_label,"alert_id":str(alert) if alert else None,"watchlist_match":bool(watchlist_match),"confidence":confidence,"kind":kind}


class TestSightingStoreContract(unittest.TestCase):
    def test_missing_identity_rejected(self):
        with self.assertRaises(ValueError): persist({b"session_id": b"", b"detection_id": b""})

    def test_timestamp_falls_back_safely(self):
        before = datetime.now(timezone.utc); parsed = _timestamp({}); after = datetime.now(timezone.utc)
        self.assertGreaterEqual(parsed, before); self.assertLessEqual(parsed, after)

    def test_plate_normalization_is_stable(self):
        self.assertEqual("GJ01AB1234", normalize_plate("gj 01-ab 1234"))

    def test_unconfirmed_plate_is_not_a_business_alert(self):
        self.assertFalse(_truthy({b"plate_validated": b"1", b"anpr_consensus": b"0"}, "anpr_consensus"))


if __name__ == "__main__": unittest.main()
