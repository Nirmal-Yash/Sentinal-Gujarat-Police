from datetime import datetime, timezone
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from auth import Principal, require_permission
from database import get_db
from plate_normalise import normalize_plate
from demo_route import geo_for_stream
from alert_summary import build_human_summary
from alert_filters import alert_type_filter_clause, alert_sort_expression

router = APIRouter(prefix="/test/sessions", tags=["test-alerts"])
VALID = {"NEW": {"ACKNOWLEDGED"}, "ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"}, "INVESTIGATING": {"RESOLVED"}, "RESOLVED": {"CLOSED"}, "CLOSED": set()}

async def _test_alert_public(row):
    details = dict(row.get("details") or {})
    camera = None
    stream_id = row.get("stream_id")
    cam_name = row.get("cam_name") or (f"Test Camera {stream_id}" if stream_id is not None else None)
    if stream_id is not None:
        geo = geo_for_stream(int(stream_id))
        camera = {
            "id": f"test-{row['session_id']}-{stream_id}",
            "name": cam_name,
            "location": geo["location"],
            "coordinates": {"lat": geo["lat"], "lng": geo["lng"]},
            "department": geo["department"],
        }
    return {
        "id": row["id"],
        "alert_id": row["id"],
        "session_id": row["session_id"],
        "cam_id": camera["id"] if camera else None,
        "cam_name": camera["name"] if camera else None,
        "camera_label": camera["name"] if camera else None,
        "alert_type": row["alert_type"],
        "priority": row["priority"],
        "severity": row["priority"],
        "entity_type": row.get("entity_type"),
        "details": details,
        "acknowledged": bool(row["acknowledged"]),
        "status": row["status"] or ("ACKNOWLEDGED" if row["acknowledged"] else "NEW"),
        "event_at": row.get("event_at") or row["created_at"],
        "created_at": row.get("event_at") or row["created_at"],
        "updated_at": row["updated_at"],
        "acknowledged_at": row["acknowledged_at"],
        "acknowledged_by": row["acknowledged_by"],
        "resolved_at": row["resolved_at"],
        "resolved_by": row["resolved_by"],
        "closed_at": row["closed_at"],
        "closed_by": row["closed_by"],
        "human_summary": details.get("human_summary") or build_human_summary(row.get("alert_type"), details, cam_name or "test camera"),
        "location": camera["location"] if camera else None,
        "lat": camera["coordinates"]["lat"] if camera else None,
        "lng": camera["coordinates"]["lng"] if camera else None,
        "camera": camera,
        "detected_at": row["created_at"],
        "detection_detail": details.get("detection_detail") or {},
        "evidence": details.get("evidence") or {"available": False, "description": "Test evidence unavailable."},
    }


@router.get("/{session_id}/alerts")
async def list_test_alerts(
    session_id: uuid.UUID,
    priority: str | None = Query(None, max_length=16),
    alert_type: str | None = Query(None, max_length=64),
    status: str | None = Query(None, max_length=24),
    camera: str | None = Query(None, max_length=100),
    plate: str | None = Query(None, max_length=20),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    limit: int = Query(300, ge=1, le=300),
    _: Principal = Depends(require_permission("alert:read")),
    db: AsyncSession = Depends(get_db),
):
    if priority and priority.lower() in {"undefined", "null"}: priority = None
    if status and status.lower() in {"undefined", "null"}: status = None
    if alert_type and alert_type.lower() in {"undefined", "null"}: alert_type = None

    clauses = ["a.session_id=CAST(:session_id AS uuid)"]
    params = {"session_id": str(session_id), "limit": limit}
    if priority:
        clauses.append("a.priority = upper(:priority)")
        params["priority"] = priority
    if alert_type:
        type_clause, type_params = alert_type_filter_clause(alert_type)
        if type_clause:
            clauses.append(type_clause)
            params.update(type_params)
    if status:
        clauses.append("COALESCE(a.status, CASE WHEN a.acknowledged THEN 'ACKNOWLEDGED' ELSE 'NEW' END) = upper(:status)")
        params["status"] = status
    if camera:
        clauses.append("COALESCE(d.camera_label, a.details->>'camera_label', '') ILIKE :camera")
        params["camera"] = f"%{camera.strip()}%"
    if plate:
        clauses.append("COALESCE(a.details->>'plate_text', '') ILIKE :plate")
        params["plate"] = f"%{plate.strip()}%"
    if from_ts:
        clauses.append("a.created_at >= CAST(:from_ts AS timestamptz)")
        params["from_ts"] = from_ts
    if to_ts:
        clauses.append("a.created_at <= CAST(:to_ts AS timestamptz)")
        params["to_ts"] = to_ts

    sql = f"""SELECT a.id, a.session_id, a.alert_type, a.priority,
        COALESCE(d.detection_type, a.details->>'entity_type', 'unknown') AS entity_type,
        a.details, a.acknowledged, a.status,
        a.event_at, a.created_at, a.updated_at, a.acknowledged_at, a.acknowledged_by,
        a.resolved_at, a.resolved_by, a.closed_at, a.closed_by,
        COALESCE(d.stream_id, (a.details->>'stream_id')::int) AS stream_id,
        COALESCE(d.camera_label, a.details->>'camera_label') AS cam_name
        FROM test_alerts a
        LEFT JOIN test_detections d ON d.id = a.detection_id
        WHERE {" AND ".join(clauses)}
        ORDER BY {alert_sort_expression(test_mode=True)} LIMIT :limit"""

    rows = await db.execute(text(sql), params)
    return [await _test_alert_public(row) for row in rows.mappings().all()]


@router.get("/{session_id}/alerts/counts")
async def test_alert_counts(
    session_id: uuid.UUID,
    _: Principal = Depends(require_permission("alert:read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""SELECT COUNT(*) AS total,
        COUNT(*) FILTER (WHERE priority='CRITICAL') AS critical,
        COUNT(*) FILTER (WHERE priority='HIGH') AS high,
        COUNT(*) FILTER (WHERE priority='MEDIUM') AS medium,
        COUNT(*) FILTER (WHERE priority='LOW') AS low,
        COUNT(*) FILTER (WHERE COALESCE(status, CASE WHEN acknowledged THEN 'ACKNOWLEDGED' ELSE 'NEW' END)='NEW') AS unacknowledged,
        COUNT(*) FILTER (WHERE COALESCE(status, CASE WHEN acknowledged THEN 'ACKNOWLEDGED' ELSE 'NEW' END)='ACKNOWLEDGED') AS acknowledged,
        COUNT(*) FILTER (WHERE COALESCE(status, CASE WHEN acknowledged THEN 'ACKNOWLEDGED' ELSE 'NEW' END)='INVESTIGATING') AS investigating,
        COUNT(*) FILTER (WHERE COALESCE(status, CASE WHEN acknowledged THEN 'ACKNOWLEDGED' ELSE 'NEW' END)='RESOLVED') AS resolved,
        COUNT(*) FILTER (WHERE COALESCE(status, CASE WHEN acknowledged THEN 'ACKNOWLEDGED' ELSE 'NEW' END)='CLOSED') AS closed
        FROM test_alerts WHERE session_id=CAST(:session_id AS uuid)"""), {"session_id": str(session_id)})
    return dict(result.mappings().one())

@router.post("/{session_id}/alerts/{alert_id}/transition")
async def transition_test_alert(
    session_id: uuid.UUID,
    alert_id: uuid.UUID,
    target_status: str = Query(..., min_length=3, max_length=24),
    reason: str | None = Query(None, max_length=1000),
    principal: Principal = Depends(require_permission("alert:operate")),
    db: AsyncSession = Depends(get_db),
):
    target_status = target_status.upper()
    result = await db.execute(text("""SELECT id,status,acknowledged,acknowledged_at,acknowledged_by
        FROM test_alerts WHERE id=CAST(:alert_id AS uuid) AND session_id=CAST(:session_id AS uuid) FOR UPDATE"""),
        {"alert_id": str(alert_id), "session_id": str(session_id)})
    alert = result.mappings().first()
    if not alert:
        raise HTTPException(404, "Test alert not found")
    current = str(alert["status"] or ("ACKNOWLEDGED" if alert["acknowledged"] else "NEW")).upper()
    if target_status == current:
        return {"id": str(alert_id), "status": current, "idempotent": True}
    if target_status not in VALID.get(current, set()):
        raise HTTPException(409, f"Invalid test alert transition: {current} -> {target_status}")
    now = datetime.now(timezone.utc)
    clauses = ["status=:status", "updated_at=:updated_at"]
    params = {"status": target_status, "updated_at": now, "id": str(alert_id), "session_id": str(session_id)}
    if target_status == "ACKNOWLEDGED":
        clauses += ["acknowledged=TRUE", "acknowledged_at=:acknowledged_at", "acknowledged_by=:acknowledged_by"]
        params.update(acknowledged_at=now, acknowledged_by=principal.username)
    elif target_status == "INVESTIGATING":
        clauses += ["acknowledged=TRUE", "acknowledged_at=COALESCE(acknowledged_at,:acknowledged_at)", "acknowledged_by=COALESCE(acknowledged_by,:acknowledged_by)"]
        params.update(acknowledged_at=now, acknowledged_by=principal.username)
    elif target_status == "RESOLVED":
        clauses += ["resolved_at=:resolved_at", "resolved_by=:resolved_by"]
        params.update(resolved_at=now, resolved_by=principal.username)
    elif target_status == "CLOSED":
        clauses += ["closed_at=:closed_at", "closed_by=:closed_by"]
        params.update(closed_at=now, closed_by=principal.username)
    if reason:
        clauses.append("details = details || CAST(:transition_details AS jsonb)")
        params["transition_details"] = json.dumps({"transition_reason": reason, "transition_actor": principal.username})
    await db.execute(text(f"UPDATE test_alerts SET {', '.join(clauses)} WHERE id=CAST(:id AS uuid) AND session_id=CAST(:session_id AS uuid)"), params)
    await db.commit()
    return {"id": str(alert_id), "status": target_status, "actor": principal.username, "reason": reason, "idempotent": False}
