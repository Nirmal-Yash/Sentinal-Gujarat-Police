from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from models import Detection, Alert
from database import get_db
from typing import Optional
import uuid

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/plate")
async def search_plate(
    q:     str = Query(..., min_length=3, description="Plate number (partial OK)"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search detections and alerts by license plate number."""
    result = await db.execute(text("""
        SELECT d.id, d.cam_id, d.timestamp, d.plate_text,
               d.confidence, d.bbox, c.name AS cam_name
        FROM detections d
        JOIN cameras c ON c.id = d.cam_id
        WHERE d.plate_text ILIKE :pat
        ORDER BY d.timestamp DESC
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
        SELECT d.id, d.cam_id, d.timestamp, d.detection_type,
               d.confidence, d.global_track_id, c.name AS cam_name,
               c.lat, c.lng
        FROM detections d
        JOIN cameras c ON c.id = d.cam_id
        WHERE d.global_track_id = :tid
        ORDER BY d.timestamp ASC
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
