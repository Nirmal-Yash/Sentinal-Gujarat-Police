from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, text, or_, String
from sqlalchemy.ext.asyncio import AsyncSession
from models import Camera, CameraOut, CameraCreate
from database import get_db
import uuid, os, base64
import redis as redis_lib

router = APIRouter(prefix="/cameras", tags=["cameras"])
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@router.get("/", response_model=list[CameraOut])
async def list_cameras(
    q: str | None = Query(None, min_length=1, max_length=100),
    department: str | None = None, status: str | None = None,
    health_status: str | None = None, camera_type: str | None = None,
    limit: int = Query(250, ge=1, le=500), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Registry read model.  It is the only camera metadata source for UI/GIS."""
    stmt = select(Camera).where(Camera.status != 'deleted')
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Camera.name.ilike(term), Camera.location.ilike(term),
                              Camera.department.ilike(term), Camera.owner_organization.ilike(term),
                              Camera.status.ilike(term), Camera.health_status.ilike(term),
                              Camera.camera_type.ilike(term),
                              Camera.stream_id.cast(String).ilike(term)))
    for column, value in ((Camera.department, department), (Camera.status, status),
                          (Camera.health_status, health_status), (Camera.camera_type, camera_type)):
        if value:
            stmt = stmt.where(column.ilike(value))
    result = await db.execute(stmt.order_by(Camera.stream_id).limit(limit).offset(offset))
    return result.scalars().all()


@router.post("/", response_model=CameraOut, status_code=201)
async def onboard_camera(body: CameraCreate, db: AsyncSession = Depends(get_db)):
    """Manual/API Model-1 onboarding; catalogue sync remains the same owner for external sources."""
    camera = Camera(**body.model_dump())
    db.add(camera)
    await db.flush()
    await db.execute(text("UPDATE cameras SET geom=ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), updated_at=NOW() WHERE id=:id"),
                     {"id": str(camera.id), "lat": body.lat, "lng": body.lng})
    await db.execute(text("""INSERT INTO camera_audit_log(camera_id, actor, action, after_value)
        VALUES (CAST(:id AS uuid), 'api', 'create', CAST(:value AS jsonb))"""),
        {"id": str(camera.id), "value": '{"source":"manual_api"}'})
    await db.commit()
    await db.refresh(camera)
    return camera


@router.get("/export")
async def export_cameras(db: AsyncSession = Depends(get_db)):
    """Export public registry metadata only; URLs/credentials are never exported."""
    result = await db.execute(select(Camera).where(Camera.status != 'deleted').order_by(Camera.stream_id))
    headers = "id,stream_id,name,location,latitude,longitude,department,owner,camera_type,status,health_status\n"
    rows = [headers]
    for c in result.scalars():
        values = [c.id, c.stream_id, c.name, c.location, c.lat, c.lng, c.department,
                  c.owner_organization, c.camera_type, c.status, c.health_status]
        rows.append(",".join('"' + str(v or '').replace('"', '""') + '"' for v in values) + "\n")
    return Response("".join(rows), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=camera-registry.csv"})


@router.get("/geojson")
async def cameras_geojson(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera).where(Camera.status != 'deleted').order_by(Camera.stream_id))
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": str(c.id), "geometry": {"type": "Point", "coordinates": [c.lng, c.lat]},
         "properties": {"id": str(c.id), "name": c.name, "stream_id": c.stream_id,
                        "department": c.department, "camera_type": c.camera_type,
                        "status": c.status, "health_status": c.health_status}}
        for c in result.scalars()
    ]}


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
