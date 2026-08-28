from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from auth import Principal, require_role
from database import get_db

router = APIRouter(prefix="/operations", tags=["operations"])

@router.get("/cameras/{camera_id}/health")
async def camera_health_history(
    camera_id: uuid.UUID,
    minutes: int = Query(60, ge=5, le=10080),
    _: Principal = Depends(require_role("VIEWER")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        SELECT observed_at, health_status, source_fps, decode_fps, published_fps,
               reconnect_count, decode_failure_count
        FROM camera_health_observations
        WHERE camera_id=CAST(:camera_id AS uuid)
          AND observed_at >= NOW() - (:minutes * INTERVAL '1 minute')
        ORDER BY observed_at ASC
    """), {"camera_id": str(camera_id), "minutes": minutes})
    rows = [dict(row) for row in result.mappings()]
    return {"camera_id": str(camera_id), "minutes": minutes, "observations": rows}

@router.get("/cameras/health/summary")
async def camera_health_summary(
    _: Principal = Depends(require_role("VIEWER")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        SELECT health_status, COUNT(*) AS cameras
        FROM cameras
        WHERE status <> 'deleted'
        GROUP BY health_status
        ORDER BY health_status
    """))
    return {"items": [dict(row) for row in result.mappings()]}
