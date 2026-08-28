from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from auth import Principal, require_permission
from database import get_db

router = APIRouter(prefix="/operations", tags=["operations"])

@router.get("/cameras/{camera_id}/health")
async def camera_health_history(
    camera_id: uuid.UUID,
    minutes: int = Query(60, ge=5, le=10080),
    _: Principal = Depends(require_permission("camera:read")),
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
    return {"camera_id": str(camera_id), "minutes": minutes, "observations": [dict(row) for row in result.mappings()]}

@router.get("/cameras/health/summary")
async def camera_health_summary(
    _: Principal = Depends(require_permission("camera:read")),
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

@router.get("/overview")
async def operations_overview(
    _: Principal = Depends(require_permission("report:read")),
    db: AsyncSession = Depends(get_db),
):
    """Single authoritative operational snapshot for dashboards and health review."""
    result = await db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted') AS cameras_total,
          (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted' AND health_status='healthy') AS cameras_healthy,
          (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted' AND health_status IN ('reconnecting','degraded')) AS cameras_degraded,
          (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted' AND health_status='offline') AS cameras_offline,
          (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted' AND last_frame_at >= NOW() - INTERVAL '30 seconds') AS cameras_recent_frame,
          (SELECT COUNT(*) FROM detections WHERE timestamp >= NOW() - INTERVAL '5 minutes') AS detections_5m,
          (SELECT COUNT(*) FROM vehicle_sightings WHERE source_timestamp >= NOW() - INTERVAL '5 minutes') AS sightings_5m,
          (SELECT COUNT(*) FROM alerts WHERE status='NEW') AS alerts_new,
          (SELECT COUNT(*) FROM alerts WHERE created_at >= NOW() - INTERVAL '1 hour') AS alerts_1h,
          (SELECT COUNT(*) FROM vehicle_journeys WHERE status='ACTIVE') AS active_journeys,
          (SELECT COUNT(*) FROM evidence WHERE created_at >= NOW() - INTERVAL '1 hour') AS evidence_1h
    """)).mappings().one()
    return {"generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "metrics": dict(result)}
