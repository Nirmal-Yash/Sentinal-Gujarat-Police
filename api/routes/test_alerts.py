from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from models import TestAlert
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
    result = await db.execute(text("""SELECT id,status,acknowledged,acknowledged_at,acknowledged_by,resolved_at,resolved_by,closed_at,closed_by
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
    values = {"status": target_status, "updated_at": now}
    if target_status == "ACKNOWLEDGED": values.update(acknowledged=True, acknowledged_at=now, acknowledged_by=principal.username)
    elif target_status == "INVESTIGATING": values.update(acknowledged=True, acknowledged_at=alert["acknowledged_at"] or now, acknowledged_by=alert["acknowledged_by"] or principal.username)
    elif target_status == "RESOLVED": values.update(resolved_at=now, resolved_by=principal.username)
    elif target_status == "CLOSED": values.update(closed_at=now, closed_by=principal.username)
    await db.execute(update(TestAlert).where(TestAlert.id == alert_id, TestAlert.session_id == session_id).values(**values))
    await db.commit()
    return {"id": str(alert_id), "status": target_status, "actor": principal.username, "reason": reason, "idempotent": False}
