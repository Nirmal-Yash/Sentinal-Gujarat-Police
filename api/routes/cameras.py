from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from models import Camera, CameraOut
from database import get_db
import uuid, os, base64
import redis as redis_lib

router = APIRouter(prefix="/cameras", tags=["cameras"])
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@router.get("/", response_model=list[CameraOut])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Camera).where(Camera.status != 'deleted').order_by(Camera.stream_id))
    return result.scalars().all()


@router.get("/stats/summary")
async def camera_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT c.id, c.name, c.stream_id, c.status, c.codec,
               c.width, c.height, c.hls_url,
               COUNT(a.id) FILTER (WHERE a.created_at > NOW() - INTERVAL '1 hour') AS alerts_1h,
               COUNT(a.id) FILTER (WHERE a.acknowledged = FALSE)                   AS unacked
        FROM cameras c
        LEFT JOIN alerts a ON a.cam_id = c.id
        WHERE c.status != 'deleted'
        GROUP BY c.id, c.name, c.stream_id, c.status, c.codec, c.width, c.height, c.hls_url
        ORDER BY c.stream_id
    """))
    return [dict(r) for r in result.mappings().all()]


@router.get("/{cam_id}", response_model=CameraOut)
async def get_camera(cam_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, cam_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    return cam


@router.get("/{cam_id}/snapshot")
async def snapshot(cam_id: uuid.UUID):
    """Return latest JPEG frame cached by ingestion worker (10 s TTL)."""
    r    = redis_lib.from_url(REDIS_URL, decode_responses=False)
    data = r.get(f"snapshot:{cam_id}")
    if not data:
        raise HTTPException(404, "No snapshot available yet — stream may still be connecting")
    return Response(content=base64.b64decode(data), media_type="image/jpeg")


@router.get("/pipeline/stats")
async def pipeline_stats():
    """Return Redis stream lengths — proves pipeline is alive without DB queries."""
    import redis as redis_lib
    try:
        r = redis_lib.from_url(REDIS_URL, decode_responses=True)
        return {
            "raw_frames":  r.xlen("raw_frames"),
            "detections":  r.xlen("detections"),
            "alerts":      r.xlen("alerts"),
            "cam_resets":  r.xlen("cam_resets") if r.exists("cam_resets") else 0,
        }
    except Exception as e:
        return {"error": str(e)}
