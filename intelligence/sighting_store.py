"""Durable detection and vehicle-sighting persistence for the Redis pipeline."""
import json
import os
from datetime import datetime, timezone

import psycopg2

DB_URL = os.getenv("DATABASE_URL", "")


def _text(data, key, default=""):
    value = data.get(key.encode(), default.encode() if isinstance(default, str) else default)
    return value.decode() if isinstance(value, bytes) else str(value)


def _timestamp(data):
    """Use camera source time where supplied; preserve ingestion fallback explicitly."""
    value = _text(data, "source_ts") or _text(data, "ingested_at")
    if not value:
        return datetime.now(timezone.utc), "worker_received"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc), (
            "source" if _text(data, "source_ts") else "ingested")
    except ValueError:
        return datetime.now(timezone.utc), "worker_received"


def persist(data: dict):
    """Persist before intelligence decisions; duplicate delivery is idempotent."""
    detection_id = _text(data, "detection_id") or _text(data, "event_id")
    if not detection_id:
        return None
    camera_id = _text(data, "cam_id") or None
    timestamp, timestamp_origin = _timestamp(data)
    plate = _text(data, "plate_text").upper().replace(" ", "").replace("-", "") or None
    confidence = float(_text(data, "conf", "0") or 0)
    bbox = {k: _text(data, k) for k in ("x1", "y1", "x2", "y2") if k.encode() in data}
    metadata = {
        "schema_version": _text(data, "schema_version", "1.0"),
        "event_id": _text(data, "event_id", detection_id),
        "source_timestamp_origin": timestamp_origin,
        "raw_ocr": _text(data, "raw_ocr"),
        "ocr_confidence": _text(data, "ocr_conf", ""),
        "detector_confidence": _text(data, "detector_conf", ""),
    }
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO detections
                    (id, cam_id, timestamp, pts_ms, detection_type, bbox,
                     confidence, track_id, global_track_id, plate_text, metadata)
                VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO NOTHING
            """, (detection_id, camera_id, timestamp, int(_text(data, "pts_ms", "0") or 0),
                  _text(data, "detection_type"), json.dumps(bbox), confidence,
                  _text(data, "track_id") or None,
                  _text(data, "global_track_id") or None, plate, json.dumps(metadata)))
            if plate:
                event_id = _text(data, "event_id", detection_id)
                # Plate identity is intentionally separate from a local DeepSORT
                # ID, enabling deterministic journey reconstruction across cameras.
                global_vehicle_id = _text(data, "global_track_id") or f"plate:{plate}"
                cur.execute("""
                    INSERT INTO vehicle_sightings
                      (event_id, detection_id, raw_plate, normalized_plate, camera_id,
                       source_timestamp, confidence, vehicle_type, track_id,
                       global_vehicle_id, model_versions)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (event_id) DO NOTHING
                """, (event_id, detection_id, _text(data, "raw_ocr") or plate, plate, camera_id,
                      timestamp, confidence, _text(data, "vehicle_type") or _text(data, "detection_type"),
                      _text(data, "track_id") or None, global_vehicle_id,
                      json.dumps({"detector": "yolov8", "ocr": "easyocr"})))
        conn.commit()
    finally:
        conn.close()
    return {"timestamp": timestamp, "plate": plate, "global_vehicle_id": f"plate:{plate}" if plate else None}
