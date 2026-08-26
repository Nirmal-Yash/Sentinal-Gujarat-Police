import csv, io
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth import require_role, Principal

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/detections")
async def detection_report(
    format: str = Query("json", pattern="^(json|csv)$"),
    from_at: datetime | None = None, to_at: datetime | None = None,
    cam_id: str | None = None, plate: str | None = None,
    limit: int = Query(1000, ge=1, le=10000),
    _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db),
):
    sql = """SELECT d.id, d.timestamp, d.cam_id, c.stream_id, c.name AS camera_name, c.location,
        d.detection_type, d.plate_text, d.confidence, d.track_id, d.global_track_id
        FROM detections d LEFT JOIN cameras c ON c.id=d.cam_id WHERE 1=1"""
    params = {"limit": limit}
    if from_at: sql += " AND d.timestamp >= :from_at"; params["from_at"] = from_at
    if to_at: sql += " AND d.timestamp <= :to_at"; params["to_at"] = to_at
    if cam_id: sql += " AND d.cam_id=CAST(:cam_id AS uuid)"; params["cam_id"] = cam_id
    if plate: sql += " AND d.plate_text ILIKE :plate"; params["plate"] = f"%{plate.upper().replace(' ', '')}%"
    sql += " ORDER BY d.timestamp DESC LIMIT :limit"
    rows = [dict(row) for row in (await db.execute(text(sql), params)).mappings().all()]
    if format == "json": return {"items": rows, "count": len(rows)}
    stream = io.StringIO(); fields = ["id", "timestamp", "cam_id", "stream_id", "camera_name", "location", "detection_type", "plate_text", "confidence", "track_id", "global_track_id"]
    writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sentinel-detections.csv"})
