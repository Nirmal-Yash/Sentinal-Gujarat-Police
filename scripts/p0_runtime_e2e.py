#!/usr/bin/env python3
"""P0 runtime data-plane verification with isolated PostgreSQL + Redis services."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import psycopg2
import redis

from intelligence.sighting_store import persist
from intelligence.alert_engine import AlertEngine

DB_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
CAMERA_ID = str(uuid.uuid4())


def db():
    return psycopg2.connect(DB_URL)


def setup_schema():
    # This E2E owns its schema inside a dedicated fresh CI database.  Never
    # attempt to recreate a production/bootstrap table in the shared CI DB.
    with db() as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id UUID PRIMARY KEY, stream_id INTEGER UNIQUE, name TEXT NOT NULL,
            location TEXT, lat DOUBLE PRECISION, lng DOUBLE PRECISION,
            codec TEXT, width INTEGER, height INTEGER, fps DOUBLE PRECISION
        );
        CREATE TABLE IF NOT EXISTS detections (
            id UUID PRIMARY KEY, cam_id UUID, timestamp TIMESTAMPTZ NOT NULL,
            pts_ms BIGINT DEFAULT 0, detection_type TEXT, bbox JSONB,
            confidence DOUBLE PRECISION, track_id TEXT, global_track_id TEXT,
            plate_text TEXT, metadata JSONB
        );
        CREATE TABLE IF NOT EXISTS vehicle_identities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), canonical_key TEXT UNIQUE NOT NULL,
            identity_type TEXT, normalized_plate TEXT, confidence DOUBLE PRECISION,
            provenance JSONB NOT NULL DEFAULT '{}'::jsonb, first_seen_at TIMESTAMPTZ,
            last_seen_at TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS vehicle_journeys (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), vehicle_identity_id UUID NOT NULL,
            started_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ NOT NULL,
            sighting_count INTEGER NOT NULL DEFAULT 0, journey_confidence DOUBLE PRECISION,
            status TEXT DEFAULT 'ACTIVE', created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS vehicle_sightings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(), event_id UUID UNIQUE NOT NULL,
            detection_id UUID, raw_plate TEXT, normalized_plate TEXT NOT NULL, camera_id UUID,
            source_timestamp TIMESTAMPTZ NOT NULL, confidence DOUBLE PRECISION NOT NULL,
            vehicle_type TEXT, track_id TEXT, global_vehicle_id TEXT, evidence_id TEXT,
            model_versions JSONB NOT NULL DEFAULT '{}'::jsonb, identity_type TEXT DEFAULT 'PLATE_CONFIRMED',
            observation_bucket TIMESTAMPTZ NOT NULL, journey_id UUID, created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vs ON vehicle_sightings(camera_id, normalized_plate, observation_bucket);
        CREATE TABLE IF NOT EXISTS vehicle_journey_sightings (
            journey_id UUID NOT NULL, sighting_id UUID NOT NULL, sequence_no INTEGER NOT NULL,
            PRIMARY KEY (journey_id, sighting_id), UNIQUE (journey_id, sequence_no)
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id UUID PRIMARY KEY, detection_id UUID, cam_id UUID, alert_type TEXT NOT NULL,
            priority TEXT NOT NULL, confidence DOUBLE PRECISION, entity_type TEXT,
            details JSONB, acknowledged BOOLEAN DEFAULT FALSE, acknowledged_at TIMESTAMPTZ,
            acknowledged_by TEXT, status TEXT NOT NULL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ,
            dedup_key TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS global_tracks (
            id TEXT PRIMARY KEY, entity_type TEXT, first_seen_cam UUID, last_seen_cam UUID,
            first_seen_at TIMESTAMPTZ, last_seen_at TIMESTAMPTZ, cam_history JSONB DEFAULT '[]'::jsonb,
            embedding TEXT, identity_source TEXT, last_confidence DOUBLE PRECISION, metadata JSONB DEFAULT '{}'::jsonb
        );
        """)
        cur.execute("INSERT INTO cameras(id,stream_id,name) VALUES (%s,1,'P0 E2E Camera') ON CONFLICT (stream_id) DO NOTHING", (CAMERA_ID,))
        conn.commit()


def counts():
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM detections"); detections = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM vehicle_sightings"); sightings = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM vehicle_journeys"); journeys = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM alerts"); alerts = cur.fetchone()[0]
    return {"detections": detections, "vehicle_sightings": sightings, "journeys": journeys, "alerts": alerts}


def main():
    setup_schema()
    r = redis.from_url(REDIS_URL)
    r.flushdb()
    engine = AlertEngine()
    event_time = datetime.now(timezone.utc)
    payload = {
        b"event_id": str(uuid.uuid4()).encode(), b"detection_id": str(uuid.uuid4()).encode(),
        b"session_id": b"p0", b"cam_id": CAMERA_ID.encode(), b"stream_id": b"1",
        b"source_ts": event_time.isoformat().encode(), b"ingested_at": event_time.isoformat().encode(),
        b"pts_ms": b"1000", b"detection_type": b"plate", b"plate_text": b"GJ01AB1234",
        b"raw_ocr": b"GJ 01 AB 1234", b"plate_validated": b"1", b"anpr_consensus": b"1", b"conf": b"0.93",
        b"detector_conf": b"0.94", b"ocr_conf": b"0.92", b"track_id": b"t-1",
        b"x1": b"100", b"y1": b"100", b"x2": b"300", b"y2": b"250",
        b"event_type": b"detection", b"schema_version": b"1.0",
    }
    first_start = time.perf_counter()
    first = persist(payload)
    first_latency_ms = (time.perf_counter() - first_start) * 1000

    second_start = time.perf_counter()
    second = persist({**payload, b"event_id": str(uuid.uuid4()).encode(), b"detection_id": str(uuid.uuid4()).encode(), b"pts_ms": b"1100"})
    second_latency_ms = (time.perf_counter() - second_start) * 1000

    after_sightings = counts()
    assert first["duplicate"] is False and first["business_sighting"] is True, first
    assert second["duplicate"] is True and second["business_sighting"] is True, second
    assert after_sightings["detections"] == 2, after_sightings
    assert after_sightings["vehicle_sightings"] == 1, after_sightings
    assert after_sightings["journeys"] == 1, after_sightings

    invalid = persist({**payload, b"event_id": str(uuid.uuid4()).encode(), b"detection_id": str(uuid.uuid4()).encode(), b"plate_text": b"GARBAGE", b"plate_validated": b"0", b"anpr_consensus": b"0"})
    after_invalid = counts()
    assert invalid["business_sighting"] is False, invalid
    assert after_invalid["vehicle_sightings"] == 1, after_invalid

    alert_payload = {
        "detection_id": str(uuid.UUID(payload[b"detection_id"].decode())),
        "cam_id": CAMERA_ID, "alert_type": "WATCHLIST_MATCH", "priority": "HIGH",
        "confidence": 0.94, "entity_type": "vehicle", "event_timestamp": event_time.timestamp(),
        "details": {"plate_text": "GJ01AB1234", "watchlist_id": "p0"},
    }
    alert_start = time.perf_counter()
    alert_1 = engine.fire(r, dict(alert_payload))
    alert_2 = engine.fire(r, dict(alert_payload))
    alert_latency_ms = (time.perf_counter() - alert_start) * 1000
    final = counts()
    assert bool(alert_1) and alert_2 is None, (alert_1, alert_2)
    assert final["alerts"] == 1, final
    assert r.xlen("alerts") == 1, r.xlen("alerts")

    print(json.dumps({
        "status": "PASS",
        "detection_sighting_reconciliation": {
            "detections": final["detections"],
            "business_sightings": final["vehicle_sightings"],
            "unconfirmed_plates_excluded_from_business_sightings": 1,
            "duplicate_business_sightings_suppressed": 1,
            "journeys": final["journeys"],
            "alerts": final["alerts"],
        },
        "latency_ms": {
            "first_sighting": round(first_latency_ms, 3),
            "duplicate_sighting": round(second_latency_ms, 3),
            "alert_persistence_and_publish": round(alert_latency_ms, 3),
        },
        "model_accuracy_status": "NOT_MEASURED_WITHOUT_LABELED_VIDEO_GROUND_TRUTH",
    }, indent=2))


if __name__ == "__main__":
    main()
