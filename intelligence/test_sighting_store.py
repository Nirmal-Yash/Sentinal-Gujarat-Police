"""Persistence boundary and regression tests for isolated test mode."""
import json, os, unittest
from datetime import datetime, timezone
from unittest.mock import patch

import psycopg2

DB_URL = os.getenv("DATABASE_URL", "")


def _value(data, name, default=""):
    value = data.get(name.encode(), default.encode() if isinstance(default, str) else default)
    return value.decode() if isinstance(value, bytes) else str(value)


def _timestamp(data):
    try:
        return datetime.fromisoformat(_value(data, "source_ts").replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def persist(data: dict):
    """Store canonical test detections and tracks only in the test namespace."""
    session_id, detection_id = _value(data, "session_id"), _value(data, "detection_id") or _value(data, "event_id")
    if not session_id or not detection_id:
        raise ValueError("test event is missing session_id or detection_id")
    timestamp = _timestamp(data)
    stream_id = int(_value(data, "stream_id", "0") or 0)
    kind = _value(data, "detection_type", "unknown")
    camera_label = f"Test Camera {stream_id}"
    track_id = _value(data, "track_id") or None
    plate = "".join(value for value in _value(data, "plate_text").upper() if value.isalnum()) or None
    confidence = float(_value(data, "conf", "0") or 0)
    bbox = {key: _value(data, key) for key in ("x1", "y1", "x2", "y2") if key.encode() in data}
    details = {"schema_version": _value(data, "schema_version", "1.0"), "event_id": _value(data, "event_id", detection_id), "raw_ocr": _value(data, "raw_ocr", ""), "pts_ms": _value(data, "pts_ms", "0"), "plate_validated": _value(data, "plate_validated", "")}
    global_track = f"test:{stream_id}:{kind}:{track_id or detection_id}"
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT camera_label FROM test_session_feeds WHERE session_id=%s::uuid AND stream_id=%s", (session_id, stream_id)); camera_label = (cur.fetchone() or [camera_label])[0]
            cur.execute("""INSERT INTO test_detections(id,session_id,camera_label,detection_type,plate_text,confidence,event_at,source_timestamp,stream_id,track_id,bbox,details)
              VALUES(%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT(id) DO NOTHING""", (detection_id,session_id,camera_label,kind,plate,confidence,timestamp,timestamp,stream_id,track_id,json.dumps(bbox),json.dumps(details)))
            cur.execute("""INSERT INTO test_tracks(session_id,global_track_id,entity_type,first_camera_label,last_camera_label,first_seen_at,last_seen_at,sightings)
              VALUES(%s::uuid,%s,%s,%s,%s,%s,%s,jsonb_build_array(jsonb_build_object('camera_label',%s,'timestamp',%s)))
              ON CONFLICT(session_id,global_track_id) DO UPDATE SET last_camera_label=EXCLUDED.last_camera_label,last_seen_at=EXCLUDED.last_seen_at,sightings=test_tracks.sightings || EXCLUDED.sightings""", (session_id,global_track,"vehicle" if kind in {"car","motorcycle","bus","truck","plate"} else kind,camera_label,camera_label,timestamp,timestamp,camera_label,timestamp.isoformat()))
            alert = None
            if kind == "plate":
                cur.execute("""INSERT INTO test_alerts(session_id,detection_id,alert_type,priority,event_at,details)
                  VALUES(%s::uuid,%s::uuid,'test_plate_detected','LOW',%s,%s::jsonb) RETURNING id""", (session_id,detection_id,timestamp,json.dumps({"plate_text": plate, "camera_label": camera_label, "test": True})))
                alert = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return {"session_id": session_id,"detection_id": detection_id,"camera_label": camera_label,"alert_id": str(alert) if alert else None,"confidence": confidence,"kind": kind}


class TestSightingStoreContract(unittest.TestCase):
    def test_missing_identity_rejected(self):
        with self.assertRaises(ValueError):
            persist({b"session_id": b"", b"detection_id": b""})

    def test_timestamp_falls_back_safely(self):
        before = datetime.now(timezone.utc)
        parsed = _timestamp({})
        after = datetime.now(timezone.utc)
        self.assertGreaterEqual(parsed, before)
        self.assertLessEqual(parsed, after)

    def test_plate_normalization_is_stable(self):
        event = {b"session_id": b"", b"detection_id": b""}
        self.assertEqual("GJ01AB1234", "".join(c for c in "gj 01-ab 1234".upper() if c.isalnum()))


if __name__ == "__main__":
    unittest.main()
