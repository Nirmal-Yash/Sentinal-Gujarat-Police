"""Demo vehicle route configuration for isolated Test Mode."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from plate_normalise import normalize_plate
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from test_geo import test_geo_for_stream

CONFIG_CANDIDATES = (
    Path(__file__).resolve().parent / "config" / "test_vehicle_route.json",
    Path(__file__).resolve().parent.parent / "config" / "test_vehicle_route.json",
    Path("/app/config/test_vehicle_route.json"),
)


def load_demo_route_config() -> dict:
    for path in CONFIG_CANDIDATES:
        if path.is_file():
            with path.open(encoding="utf-8") as fh:
                return json.load(fh)
    return {"demo_plate": "GJ01AB1234", "feeds": []}


def demo_plate() -> str:
    return normalize_plate(load_demo_route_config().get("demo_plate")) or "GJ01AB1234"


def geo_index_for_stream(stream_id: int) -> int | None:
    for feed in load_demo_route_config().get("feeds") or []:
        if int(feed.get("stream_id") or 0) == int(stream_id):
            value = feed.get("geo_index")
            return int(value) if value is not None else None
    return None


def geo_for_stream(stream_id: int) -> dict:
    return test_geo_for_stream(int(stream_id), geo_index_for_stream(stream_id))


async def seed_demo_route_data(session_id: uuid.UUID, db: AsyncSession) -> dict:
    """Insert demo plate sightings across active test feeds for GIS route demo."""
    plate = demo_plate()
    feeds = (await db.execute(text("""
        SELECT stream_id, camera_label
        FROM test_session_feeds
        WHERE session_id = CAST(:session AS uuid)
        ORDER BY stream_id
    """), {"session": str(session_id)})).mappings().all()
    if not feeds:
        raise ValueError("No test feeds attached to this session")

    await db.execute(text("""
        DELETE FROM test_alerts
        WHERE session_id = CAST(:session AS uuid)
          AND details->>'demo_route' = 'true'
    """), {"session": str(session_id)})
    await db.execute(text("""
        DELETE FROM test_detections
        WHERE session_id = CAST(:session AS uuid)
          AND COALESCE(details->>'demo_route', '') = 'true'
    """), {"session": str(session_id)})

    base_time = datetime.now(timezone.utc) - timedelta(hours=2)
    track_id = f"demo-{plate.lower()}"
    detection_rows = []

    for index, feed in enumerate(feeds):
        stream_id = int(feed["stream_id"])
        label = feed["camera_label"] or f"Test Camera {stream_id}"
        geo = geo_for_stream(stream_id)
        event_at = base_time + timedelta(minutes=20 * index)
        detection_id = uuid.uuid4()
        details = {
            "demo_route": True,
            "plate_validated": True,
            "anpr_consensus": "0.94",
            "raw_ocr": plate,
            "human_summary": f"Vehicle {plate} sighted at {label}.",
            "location": geo["location"],
            "lat": geo["lat"],
            "lng": geo["lng"],
        }
        await db.execute(text("""
            INSERT INTO test_detections(
                id, session_id, camera_label, detection_type, plate_text, confidence,
                event_at, source_timestamp, stream_id, track_id, bbox, details
            ) VALUES (
                CAST(:id AS uuid), CAST(:session AS uuid), :label, 'vehicle_sighting', :plate, :confidence,
                :event_at, :event_at, :stream_id, :track_id, CAST(:bbox AS jsonb), CAST(:details AS jsonb)
            )
        """), {
            "id": str(detection_id),
            "session": str(session_id),
            "label": label,
            "plate": plate,
            "confidence": 0.94 - (index * 0.02),
            "event_at": event_at,
            "stream_id": stream_id,
            "track_id": track_id,
            "bbox": json.dumps({"x1": 120, "y1": 280, "x2": 260, "y2": 330}),
            "details": json.dumps(details),
        })
        detection_rows.append({
            "id": str(detection_id),
            "stream_id": stream_id,
            "camera_label": label,
            "event_at": event_at,
            "location": geo["location"],
            "lat": geo["lat"],
            "lng": geo["lng"],
        })

    watchlist = (await db.execute(text("""
        SELECT id, name, alert_priority
        FROM test_watchlists
        WHERE session_id = CAST(:session AS uuid)
          AND is_active = TRUE
          AND regexp_replace(upper(COALESCE(plate_number, '')), '[^A-Z0-9]', '', 'g') = :plate
        ORDER BY created_at DESC
        LIMIT 1
    """), {"session": str(session_id), "plate": plate})).mappings().first()

    if not watchlist:
        watchlist = (await db.execute(text("""
            INSERT INTO test_watchlists(session_id, name, entity_type, description, plate_number, alert_priority, is_active)
            VALUES (CAST(:session AS uuid), :name, 'vehicle', :description, :plate, 'CRITICAL', TRUE)
            RETURNING id, name, alert_priority
        """), {
            "session": str(session_id),
            "name": "Demo Watchlist Vehicle",
            "description": "Pre-seeded evaluator demo plate",
            "plate": plate,
        })).mappings().one()

    for row in detection_rows:
        alert_details = {
            "demo_route": True,
            "plate_text": plate,
            "camera_label": row["camera_label"],
            "watchlist_id": str(watchlist["id"]),
            "watchlist_name": watchlist["name"],
            "description": "Pre-seeded evaluator demo plate",
            "track_id": track_id,
            "test": True,
            "anpr_consensus": "0.94",
            "raw_ocr": plate,
            "detector_confidence": "0.94",
            "location": row["location"],
            "lat": row["lat"],
            "lng": row["lng"],
            "human_summary": f"Watchlist target {plate} identified at {row['camera_label']}.",
        }
        await db.execute(text("""
            INSERT INTO test_alerts(session_id, detection_id, alert_type, priority, event_at, details)
            VALUES (CAST(:session AS uuid), CAST(:det_id AS uuid), 'watchlist_match', :priority, :event_at, CAST(:details AS jsonb))
        """), {
            "session": str(session_id),
            "det_id": row["id"],
            "priority": watchlist["alert_priority"] or "CRITICAL",
            "event_at": row["event_at"],
            "details": json.dumps(alert_details),
        })

    await db.commit()
    return {
        "plate": plate,
        "session_id": str(session_id),
        "sightings_seeded": len(detection_rows),
        "feeds": len(feeds),
        "watchlist_id": str(watchlist["id"]),
    }
