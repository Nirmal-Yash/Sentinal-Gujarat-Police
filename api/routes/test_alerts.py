from datetime import datetime, timezone
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from auth import Principal, require_role
from database import get_db

router = APIRouter(prefix="/test/sessions", tags=["test-alerts"])
VALID = {"NEW": {"ACKNOWLEDGED"}, "ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"}, "INVESTIGATING": {"RESOLVED"}, "RESOLVED": {"CLOSED"}, "CLOSED": set()}

@router.post("/{session_id}/alerts/{alert_id}/transition")
async def transition_test_alert(
    session_id: uuid.UUID,
    alert_id: uuid.UUID,
    target_status: str = Query(..., min_length=3, max_length=24),
    reason: str | None = Query(None, max_length=1000),
    principal: Principal = Depends(require_role("ADMIN")),
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
