from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from models import Detection, Alert
from auth import require_authenticated
from database import get_db
from typing import Optional
import uuid

router = APIRouter(prefix="/search", tags=["search"], dependencies=[Depends(require_authenticated)])


@router.get("/cameras")
async def search_cameras(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Indexed registry search; deliberately returns a small read model."""
    result = await db.execute(text("""
        SELECT id, stream_id, name, location, lat, lng, hls_url, whep_url,
               ('https://live.corp8.cloud/stream/' || stream_id::text) AS stream_url, department,
               owner_organization, camera_type, status, health_status,
               COALESCE(observed_codec, codec) AS effective_codec,
               COALESCE(observed_width, width) AS effective_width,
               COALESCE(observed_height, height) AS effective_height,
               COALESCE(observed_fps, fps) AS effective_fps
        FROM cameras
        WHERE status <> 'deleted' AND (
          name ILIKE :pattern OR location ILIKE :pattern OR department ILIKE :pattern
          OR owner_organization ILIKE :pattern OR camera_type ILIKE :pattern
          OR status ILIKE :pattern OR health_status ILIKE :pattern
          OR stream_id::text ILIKE :pattern
        )
        ORDER BY similarity(name, :needle) DESC, stream_id
        LIMIT :limit OFFSET :offset
    """), {"needle": q.strip(), "pattern": f"%{q.strip()}%", "limit": limit, "offset": offset})
    return {"query": q, "items": [dict(row) for row in result.mappings()], "limit": limit, "offset": offset}


@router.get("/plate")
async def search_plate(
    q:     str = Query(..., min_length=3, description="Plate number (partial OK)"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search durable vehicle sightings, not transient Redis detections."""
    result = await db.execute(text("""
        SELECT s.id, s.camera_id AS cam_id, s.source_timestamp AS timestamp,
               s.normalized_plate AS plate_text, s.confidence, c.name AS cam_name,
               c.location, c.lat, c.lng, s.track_id, s.global_vehicle_id
        FROM vehicle_sightings s
        JOIN cameras c ON c.id = s.camera_id
        WHERE s.normalized_plate ILIKE :pat
        ORDER BY s.source_timestamp DESC
        LIMIT :limit
    """), {"pat": f"%{q.upper().replace(' ','')}%", "limit": limit})
    rows = result.mappings().all()

    # Also check watchlist
    wl_result = await db.execute(text("""
        SELECT id, name, description, alert_priority
        FROM watchlist
        WHERE plate_number ILIKE :pat AND is_active = TRUE
    """), {"pat": f"%{q.upper().replace(' ','')}%"})
    watchlist_hits = [dict(r) for r in wl_result.mappings().all()]

    return {
        "query":          q,
        "detections":     [dict(r) for r in rows],
        "watchlist_hits": watchlist_hits,
    }


@router.get("/track/{global_track_id}")
async def search_by_track(global_track_id: str,
                           db: AsyncSession = Depends(get_db)):
    """Get full camera journey for a global track ID."""
    result = await db.execute(text("""
        SELECT s.id, s.camera_id AS cam_id, s.source_timestamp AS timestamp,
               s.vehicle_type AS detection_type, s.confidence,
               s.global_vehicle_id AS global_track_id, c.name AS cam_name,
               c.lat, c.lng
        FROM vehicle_sightings s
        JOIN cameras c ON c.id = s.camera_id
        WHERE s.global_vehicle_id = :tid OR s.track_id = :tid
        ORDER BY s.source_timestamp ASC
    """), {"tid": global_track_id})
    rows = [dict(r) for r in result.mappings().all()]
    return {"global_track_id": global_track_id, "sightings": rows}


@router.get("/alerts/recent")
async def recent_alerts(
    minutes: int = Query(60, le=1440),
    priority: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = """
        SELECT a.id, a.alert_type, a.priority, a.confidence,
               a.entity_type, a.details, a.created_at,
               c.name AS cam_name, c.lat, c.lng
        FROM alerts a
        LEFT JOIN cameras c ON c.id = a.cam_id
        WHERE a.created_at > NOW() - (:minutes || ' minutes')::INTERVAL
    """
    params = {"minutes": minutes}
    if priority:
        q += " AND a.priority = :priority"
        params["priority"] = priority.upper()
    q += " ORDER BY a.created_at DESC LIMIT 200"
    result = await db.execute(text(q), params)
    return [dict(r) for r in result.mappings().all()]
