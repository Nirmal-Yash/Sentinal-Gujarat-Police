import csv
import io
import re
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth import require_permission, Principal

router = APIRouter(prefix="/reports", tags=["reports"])


def _plate(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


REPORT_PERMISSION = Depends(require_permission("report:read"))


@router.get("/detections")
async def detection_report(
    format: str = Query("json", pattern="^(json|csv)$"),
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    cam_id: str | None = None,
    plate: str | None = None,
    limit: int = Query(1000, ge=1, le=10000),
    _: Principal = REPORT_PERMISSION,
    db: AsyncSession = Depends(get_db),
):
    """Unified analytics/business report; plate-filtered output comes from durable sightings."""
    params = {"limit": limit}
    if plate:
        normalized = _plate(plate)
        sql = """SELECT s.id, s.source_timestamp AS timestamp, s.camera_id AS cam_id, c.stream_id,
                 c.name AS camera_name, c.location, 'vehicle_sighting' AS detection_type,
                 s.normalized_plate AS plate_text, s.confidence, s.track_id, s.global_vehicle_id,
                 s.journey_id
                 FROM vehicle_sightings s LEFT JOIN cameras c ON c.id=s.camera_id WHERE 1=1"""
        params["plate"] = f"%{normalized}%"
        sql += " AND s.normalized_plate ILIKE :plate"
    else:
        sql = """SELECT d.id, d.timestamp, d.cam_id, c.stream_id, c.name AS camera_name, c.location,
                 d.detection_type, d.plate_text, d.confidence, d.track_id, d.global_track_id,
                 NULL::uuid AS journey_id
                 FROM detections d LEFT JOIN cameras c ON c.id=d.cam_id WHERE 1=1"""
    if from_at:
        sql += " AND d.timestamp >= :from_at" if not plate else " AND s.source_timestamp >= :from_at"; params["from_at"] = from_at
    if to_at:
        sql += " AND d.timestamp <= :to_at" if not plate else " AND s.source_timestamp <= :to_at"; params["to_at"] = to_at
    if cam_id:
        sql += " AND d.cam_id=CAST(:cam_id AS uuid)" if not plate else " AND s.camera_id=CAST(:cam_id AS uuid)"; params["cam_id"] = cam_id
    sql += " ORDER BY timestamp DESC LIMIT :limit"
    rows = [dict(row) for row in (await db.execute(text(sql), params)).mappings().all()]
    if format == "json":
        return {"items": rows, "count": len(rows)}
    stream = io.StringIO()
    fields = ["id", "timestamp", "cam_id", "stream_id", "camera_name", "location", "detection_type", "plate_text", "confidence", "track_id", "global_track_id", "journey_id"]
    writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sentinel-detections.csv"})


@router.get("/vehicle-sightings")
async def vehicle_sighting_report(
    format: str = Query("json", pattern="^(json|csv)$"),
    from_at: datetime | None = None, to_at: datetime | None = None,
    cam_id: str | None = None, plate: str | None = None,
    limit: int = Query(1000, ge=1, le=10000),
    _: Principal = REPORT_PERMISSION, db: AsyncSession = Depends(get_db),
):
    """Durable investigation report; one row represents a business sighting, not a frame."""
    params = {"limit": limit}
    sql = """SELECT s.id, s.source_timestamp AS timestamp, s.camera_id AS cam_id,
             c.stream_id, c.name AS camera_name, c.location, c.lat, c.lng,
             s.normalized_plate AS plate_text, s.raw_plate, s.confidence,
             s.vehicle_type, s.track_id, s.global_vehicle_id, s.journey_id,
             s.identity_type, s.observation_bucket
             FROM vehicle_sightings s LEFT JOIN cameras c ON c.id=s.camera_id WHERE 1=1"""
    if from_at:
        sql += " AND s.source_timestamp >= :from_at"; params["from_at"] = from_at
    if to_at:
        sql += " AND s.source_timestamp <= :to_at"; params["to_at"] = to_at
    if cam_id:
        sql += " AND s.camera_id=CAST(:cam_id AS uuid)"; params["cam_id"] = cam_id
    if plate:
        sql += " AND s.normalized_plate ILIKE :plate"; params["plate"] = f"%{_plate(plate)}%"
    sql += " ORDER BY s.source_timestamp DESC LIMIT :limit"
    rows = [dict(row) for row in (await db.execute(text(sql), params)).mappings().all()]
    if format == "json":
        return {"items": rows, "count": len(rows)}
    stream = io.StringIO(); fields = list(rows[0].keys()) if rows else ["id","timestamp","cam_id","stream_id","camera_name","location","lat","lng","plate_text","raw_plate","confidence","vehicle_type","track_id","global_vehicle_id","journey_id","identity_type","observation_bucket"]
    writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sentinel-vehicle-sightings.csv"})


@router.get("/reconciliation")
async def runtime_reconciliation(
    seconds: int = Query(300, ge=10, le=86400),
    cam_id: str | None = None,
    _: Principal = REPORT_PERMISSION,
    db: AsyncSession = Depends(get_db),
):
    """Operational reconciliation between high-volume detections and durable business records."""
    params = {"seconds": seconds}
    camera_filter = " AND d.cam_id=CAST(:cam_id AS uuid)" if cam_id else ""
    if cam_id: params["cam_id"] = cam_id
    row = (await db.execute(text(f"""
        WITH det AS (
          SELECT COUNT(*) AS total,
                 COUNT(*) FILTER (WHERE track_id IS NOT NULL) AS tracked,
                 COUNT(*) FILTER (WHERE plate_text IS NOT NULL AND plate_text <> '') AS with_plate
          FROM detections d
          WHERE d.timestamp >= NOW() - (:seconds * INTERVAL '1 second'){camera_filter}
        ), sight AS (
          SELECT COUNT(*) AS business_sightings,
                 COUNT(DISTINCT normalized_plate) AS distinct_plates
          FROM vehicle_sightings s
          WHERE s.source_timestamp >= NOW() - (:seconds * INTERVAL '1 second')
            {(' AND s.camera_id=CAST(:cam_id AS uuid)' if cam_id else '')}
        ), al AS (
          SELECT COUNT(*) AS alerts,
                 COUNT(*) FILTER (WHERE status='NEW') AS new_alerts
          FROM alerts a
          WHERE a.created_at >= NOW() - (:seconds * INTERVAL '1 second')
            {(' AND a.cam_id=CAST(:cam_id AS uuid)' if cam_id else '')}
        )
        SELECT * FROM det CROSS JOIN sight CROSS JOIN al
    """), params)).mappings().one()
    data = dict(row)
    data["sighting_per_plate_detection_ratio"] = round(data["business_sightings"] / data["with_plate"], 4) if data["with_plate"] else None
    data["business_sighting_per_detection_ratio"] = round(data["business_sightings"] / data["total"], 4) if data["total"] else None
    data["status"] = "PASS" if data["business_sightings"] <= data["with_plate"] and data["alerts"] >= data["new_alerts"] else "REVIEW"
    return data
