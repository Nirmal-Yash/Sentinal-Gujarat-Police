from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from auth import require_authenticated, Principal
from database import get_db
from models import PlateInvestigateRequest
from plate_normalise import normalize_plate
import uuid

router = APIRouter(prefix="/investigate", tags=["investigate"], dependencies=[Depends(require_authenticated)])


@router.post("/plate")
async def investigate_plate(
    body: PlateInvestigateRequest,
    x_test_session_id: str | None = Header(None, alias="X-Test-Session-Id"),
    db: AsyncSession = Depends(get_db),
):
    normalized = normalize_plate(body.plate) or body.plate.strip().upper()

    if x_test_session_id:
        try:
            session_uuid = str(uuid.UUID(x_test_session_id))
        except ValueError as exc:
            raise HTTPException(400, "Invalid X-Test-Session-Id") from exc

        result = await db.execute(
            text("""
                SELECT td.id, td.stream_id AS cam_id, td.event_at AS timestamp, td.plate_text, td.confidence,
                       COALESCE(f.camera_label, td.camera_label) AS cam_name, NULL AS location, NULL AS lat, NULL AS lng,
                       td.track_id, NULL AS global_vehicle_id, NULL AS journey_id
                FROM test_detections td
                LEFT JOIN test_session_feeds f ON f.session_id=td.session_id AND f.stream_id=td.stream_id
                WHERE td.session_id=CAST(:session AS uuid)
                  AND regexp_replace(upper(COALESCE(td.plate_text,'')), '[^A-Z0-9]', '', 'g') = :plate
                ORDER BY td.event_at DESC LIMIT 50
            """),
            {"session": session_uuid, "plate": normalized},
        )
        rows = [dict(r) for r in result.mappings().all()]
        wl = await db.execute(
            text("""
                SELECT id, name, description, alert_priority
                FROM test_watchlists
                WHERE session_id=CAST(:session AS uuid)
                  AND regexp_replace(upper(COALESCE(plate_number,'')), '[^A-Z0-9]', '', 'g') = :plate
                  AND is_active=TRUE
            """),
            {"session": session_uuid, "plate": normalized},
        )
        journeys = []
    else:
        result = await db.execute(
            text("""
                SELECT s.id, s.camera_id AS cam_id, s.source_timestamp AS timestamp,
                       s.normalized_plate AS plate_text, s.confidence, c.name AS cam_name,
                       c.location, c.lat, c.lng, s.track_id, s.global_vehicle_id, s.journey_id
                FROM vehicle_sightings s
                JOIN cameras c ON c.id=s.camera_id
                WHERE s.normalized_plate = :plate OR s.plate_text = :plate
                ORDER BY s.source_timestamp DESC LIMIT 50
            """),
            {"plate": normalized},
        )
        rows = [dict(r) for r in result.mappings().all()]
        wl = await db.execute(
            text("""
                SELECT id, name, description, alert_priority
                FROM watchlist
                WHERE regexp_replace(upper(COALESCE(plate_number,'')), '[^A-Z0-9]', '', 'g') = :plate
                  AND is_active=TRUE
            """),
            {"plate": normalized},
        )
        journeys = [
            dict(r)
            for r in (
                await db.execute(
                    text("""
                        SELECT j.id, j.started_at, j.ended_at, j.sighting_count, j.journey_confidence, j.status
                        FROM vehicle_journeys j
                        JOIN vehicle_identities v ON v.id=j.vehicle_identity_id
                        WHERE v.normalized_plate=:plate
                        ORDER BY j.started_at DESC LIMIT 20
                    """),
                    {"plate": normalized},
                )
            ).mappings().all()
        ]

    return {
        "plate": normalized,
        "query": body.plate,
        "detections": rows,
        "watchlist_hits": [dict(r) for r in wl.mappings().all()],
        "journeys": journeys,
        "session_id": x_test_session_id,
    }
