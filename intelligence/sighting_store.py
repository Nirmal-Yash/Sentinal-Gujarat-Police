"""Durable analytics, vehicle identity/sighting/journey and person re-identification persistence."""
import json, os
from datetime import datetime, timezone, timedelta
import psycopg2

DB_URL = os.getenv("DATABASE_URL", "")
CROSS_CAM_WINDOW = max(30, int(os.getenv("CROSS_CAM_WINDOW", "300")))
SIGHTING_BUCKET_SECS = max(5, int(os.getenv("SIGHTING_DEDUP_BUCKET_SECS", "30")))


def normalize_plate(value: str | None) -> str | None:
    normalized = "".join(char for char in (value or "").upper() if char.isalnum())
    return normalized or None


def _text(data, key, default=""):
    value = data.get(key.encode(), default.encode() if isinstance(default, str) else default)
    return value.decode() if isinstance(value, bytes) else str(value)


def _timestamp(data):
    value = _text(data, "source_ts") or _text(data, "ingested_at")
    if not value:
        return datetime.now(timezone.utc), "worker_received"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc), ("source" if _text(data, "source_ts") else "ingested")
    except ValueError:
        return datetime.now(timezone.utc), "worker_received"


def _upsert_journey(cur, vehicle_id: str, plate: str, timestamp: datetime, camera_id: str | None, confidence: float, sighting_id: str):
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (vehicle_id,))
    cur.execute("""INSERT INTO vehicle_identities
        (canonical_key,identity_type,normalized_plate,confidence,first_seen_at,last_seen_at,provenance)
        VALUES (%s,'PLATE_CONFIRMED',%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (canonical_key) DO UPDATE SET
          confidence=GREATEST(COALESCE(vehicle_identities.confidence,0),COALESCE(EXCLUDED.confidence,0)),
          first_seen_at=LEAST(COALESCE(vehicle_identities.first_seen_at,EXCLUDED.first_seen_at),EXCLUDED.first_seen_at),
          last_seen_at=GREATEST(COALESCE(vehicle_identities.last_seen_at,EXCLUDED.last_seen_at),EXCLUDED.last_seen_at),
          updated_at=NOW()""",
        (vehicle_id, plate, confidence, timestamp, timestamp, json.dumps({"source": "anpr", "identity_method": "plate_confirmed"})))
    cur.execute("SELECT id FROM vehicle_identities WHERE canonical_key=%s", (vehicle_id,))
    identity_id = cur.fetchone()[0]
    cur.execute("""SELECT id FROM vehicle_journeys
                   WHERE vehicle_identity_id=%s AND ended_at >= %s
                   ORDER BY ended_at DESC LIMIT 1
                   FOR UPDATE""", (identity_id, timestamp - timedelta(seconds=CROSS_CAM_WINDOW)))
    journey = cur.fetchone()
    if journey:
        journey_id = journey[0]
        cur.execute("""UPDATE vehicle_journeys
                       SET ended_at=GREATEST(ended_at,%s), sighting_count=sighting_count+1,
                           journey_confidence=GREATEST(COALESCE(journey_confidence,0),%s),
                           updated_at=NOW() WHERE id=%s""", (timestamp, confidence, journey_id))
    else:
        cur.execute("""INSERT INTO vehicle_journeys
                       (vehicle_identity_id,started_at,ended_at,sighting_count,journey_confidence,status)
                       VALUES (%s,%s,%s,1,%s,'ACTIVE') RETURNING id""", (identity_id, timestamp, timestamp, confidence))
        journey_id = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(MAX(sequence_no),0)+1 FROM vehicle_journey_sightings WHERE journey_id=%s", (journey_id,))
    sequence_no = cur.fetchone()[0]
    cur.execute("""INSERT INTO vehicle_journey_sightings(journey_id,sighting_id,sequence_no)
                   VALUES (%s,%s::uuid,%s) ON CONFLICT (journey_id,sighting_id) DO NOTHING""", (journey_id, sighting_id, sequence_no))
    return str(journey_id)


def persist(data: dict):
    """Persist analytics and at most one business sighting per camera/plate/time bucket."""
    detection_id = _text(data, "detection_id") or _text(data, "event_id")
    if not detection_id:
        return None
    camera_id = _text(data, "cam_id") or None
    timestamp, timestamp_origin = _timestamp(data)
    plate = normalize_plate(_text(data, "plate_text"))
    confidence = max(0.0, min(1.0, float(_text(data, "conf", "0") or 0)))
    vehicle_id = f"plate:{plate}" if plate else None
    bbox = {key: _text(data, key) for key in ("x1", "y1", "x2", "y2") if key.encode() in data}
    metadata = {"schema_version": _text(data, "schema_version", "1.0"), "event_id": _text(data, "event_id", detection_id),
                "source_timestamp_origin": timestamp_origin, "raw_ocr": _text(data, "raw_ocr"),
                "ocr_confidence": _text(data, "ocr_conf", ""), "detector_confidence": _text(data, "detector_conf", ""),
                "plate_validated": _text(data, "plate_validated", ""), "anpr_consensus": _text(data, "anpr_consensus", "")}
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO detections
              (id,cam_id,timestamp,pts_ms,detection_type,bbox,confidence,track_id,global_track_id,plate_text,metadata)
              VALUES (%s::uuid,%s::uuid,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb)
              ON CONFLICT (id) DO NOTHING""",
              (detection_id, camera_id, timestamp, int(_text(data, "pts_ms", "0") or 0), _text(data, "detection_type"),
               json.dumps(bbox), confidence, _text(data, "track_id") or None, vehicle_id, plate, json.dumps(metadata)))
            if not plate:
                conn.commit()
                return {"timestamp": timestamp, "plate": None, "global_vehicle_id": None, "duplicate": False}

            event_id = _text(data, "event_id", detection_id)
            bucket = timestamp.replace(second=(timestamp.second // SIGHTING_BUCKET_SECS) * SIGHTING_BUCKET_SECS, microsecond=0)
            cur.execute("""INSERT INTO vehicle_sightings
              (event_id,detection_id,raw_plate,normalized_plate,camera_id,source_timestamp,confidence,vehicle_type,track_id,global_vehicle_id,model_versions,identity_type,observation_bucket)
              VALUES (%s::uuid,%s::uuid,%s,%s,%s::uuid,%s,%s,%s,%s,%s,%s::jsonb,'PLATE_CONFIRMED',%s)
              ON CONFLICT (camera_id,normalized_plate,observation_bucket)
              WHERE camera_id IS NOT NULL AND normalized_plate IS NOT NULL DO NOTHING
              RETURNING id""",
              (event_id, detection_id, _text(data, "raw_ocr") or plate, plate, camera_id, timestamp, confidence,
               _text(data, "vehicle_type") or _text(data, "detection_type"), _text(data, "track_id") or None,
               vehicle_id, json.dumps({"detector": "yolov8", "ocr": "easyocr"}), bucket))
            inserted = cur.fetchone()
            if not inserted:
                cur.execute("""SELECT id,journey_id FROM vehicle_sightings
                    WHERE camera_id=%s::uuid AND normalized_plate=%s AND observation_bucket=%s
                    ORDER BY created_at ASC LIMIT 1""", (camera_id, plate, bucket))
                duplicate = cur.fetchone()
                conn.commit()
                return {"timestamp": timestamp, "plate": plate, "global_vehicle_id": vehicle_id,
                        "journey_id": str(duplicate[1]) if duplicate and duplicate[1] else None, "duplicate": True}

            sighting_id = str(inserted[0])
            journey_id = _upsert_journey(cur, vehicle_id, plate, timestamp, camera_id, confidence, sighting_id)
            cur.execute("UPDATE vehicle_sightings SET journey_id=%s::uuid WHERE id=%s::uuid", (journey_id, sighting_id))
        conn.commit()
    finally:
        conn.close()
    return {"timestamp": timestamp, "plate": plate, "global_vehicle_id": vehicle_id, "journey_id": journey_id, "duplicate": False}


def persist_person_track(detection_id: str, global_track_id: str, camera_id: str, timestamp: datetime, confidence: float, embedding):
    vector = "[" + ",".join(str(float(value)) for value in embedding) + "]"
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE detections SET global_track_id=%s WHERE id=%s::uuid", (global_track_id, detection_id))
            cur.execute("""INSERT INTO global_tracks
              (id,entity_type,first_seen_cam,last_seen_cam,first_seen_at,last_seen_at,cam_history,embedding,identity_source,last_confidence,metadata)
              VALUES (%s,'person',%s::uuid,%s::uuid,%s,%s,jsonb_build_array(jsonb_build_object('camera_id',%s,'timestamp',%s)),%s::vector,'faiss_face_embedding',%s,%s::jsonb)
              ON CONFLICT (id) DO UPDATE SET last_seen_cam=EXCLUDED.last_seen_cam,last_seen_at=EXCLUDED.last_seen_at,
                cam_history=global_tracks.cam_history || EXCLUDED.cam_history,embedding=EXCLUDED.embedding,
                identity_source=EXCLUDED.identity_source,last_confidence=EXCLUDED.last_confidence,updated_at=NOW()""",
              (global_track_id, camera_id, camera_id, timestamp, timestamp, camera_id, timestamp.isoformat(), vector,
               confidence, json.dumps({"identity_type": "face_reidentification"})))
        conn.commit()
    finally:
        conn.close()
