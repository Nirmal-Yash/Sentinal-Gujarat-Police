from datetime import datetime, timezone
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from auth import Principal, require_permission
from database import get_db

router = APIRouter(prefix="/test/sessions", tags=["test-alerts"])
VALID = {"NEW": {"ACKNOWLEDGED"}, "ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"}, "INVESTIGATING": {"RESOLVED"}, "RESOLVED": {"CLOSED"}, "CLOSED": set()}

async def _test_alert_public(row):
    details = dict(row.get("details") or {})
    camera = None
    stream_id = row.get("stream_id")
    if stream_id is not None:
        camera = {
            "id": f"test-{row['session_id']}-{stream_id}",
            "name": row.get("cam_name") or f"Test Camera {stream_id}",
            "location": "Isolated video test",
            "coordinates": {"lat": None, "lng": None},
            "department": "Test Mode",
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
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "acknowledged_at": row["acknowledged_at"],
        "acknowledged_by": row["acknowledged_by"],
        "resolved_at": row["resolved_at"],
        "resolved_by": row["resolved_by"],
        "closed_at": row["closed_at"],
        "closed_by": row["closed_by"],
        "human_summary": details.get("human_summary") or "Test Mode alert",
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
    limit: int = Query(300, ge=1, le=300),
    _: Principal = Depends(require_permission("alert:read")),
    db: AsyncSession = Depends(get_db),
):
    if priority and priority.lower() in {"undefined", "null"}: priority = None
    if status and status.lower() in {"undefined", "null"}: status = None
    rows = await db.execute(text("""SELECT id,session_id,alert_type,priority,entity_type,details,acknowledged,status,
        created_at,updated_at,acknowledged_at,acknowledged_by,resolved_at,resolved_by,closed_at,closed_by,stream_id
        FROM test_alerts
        WHERE session_id=CAST(:session_id AS uuid)
          AND (:priority IS NULL OR priority=upper(:priority))
          AND (:alert_type IS NULL OR alert_type ILIKE '%' || :alert_type || '%')
          AND (:status IS NULL OR COALESCE(status, CASE WHEN acknowledged THEN 'ACKNOWLEDGED' ELSE 'NEW' END)=upper(:status))
        ORDER BY created_at DESC LIMIT :limit"""),
        {"session_id": str(session_id), "priority": priority, "alert_type": alert_type, "status": status, "limit": limit})
    return [await _test_alert_public(row) for row in rows.mappings().all()]


@router.get("/{session_id}/alerts/counts")
async def test_alert_counts(
    session_id: uuid.UUID,
    _: Principal = Depends(require_permission("alert:read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""SELECT COUNT(*) AS total,
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
