from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, update, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from models import Alert, AlertOut
from auth import require_authenticated, require_role, Principal
from database import get_db
from typing import Optional
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(require_authenticated)])
VALID_TRANSITIONS = {
    "NEW": {"ACKNOWLEDGED"},
    "ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"},
    "INVESTIGATING": {"RESOLVED"},
    "RESOLVED": {"CLOSED"},
    "CLOSED": set(),
}

@router.get("/", response_model=list[AlertOut])
async def list_alerts(priority: Optional[str] = None, alert_type: Optional[str] = None, cam_id: Optional[uuid.UUID] = None,
                      status: Optional[str] = None, unacked: bool = False, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                      db: AsyncSession = Depends(get_db)):
    q = select(Alert).order_by(desc(Alert.created_at)).limit(limit).offset(offset)
    if priority: q = q.where(Alert.priority == priority.upper())
    if alert_type: q = q.where(Alert.alert_type.ilike(f"%{alert_type}%"))
    if cam_id: q = q.where(Alert.cam_id == cam_id)
    if status: q = q.where(Alert.status == status.upper())
    if unacked: q = q.where(Alert.acknowledged.is_(False))
    return (await db.execute(q)).scalars().all()

async def _transition(alert_id, target, principal, db, reason=None):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if alert is None: raise HTTPException(status_code=404, detail="Alert not found")
    current = (alert.status or ("ACKNOWLEDGED" if alert.acknowledged else "NEW")).upper(); target = target.upper()
    if target == current: return {"status": current, "alert_id": str(alert_id), "idempotent": True}
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=409, detail=f"Invalid alert transition: {current} -> {target}")
    now = datetime.now(timezone.utc); values = {"status": target, "updated_at": now}
    if target == "ACKNOWLEDGED": values.update(acknowledged=True, acknowledged_at=now, acknowledged_by=principal.username)
    elif target == "RESOLVED": values.update(resolved_at=now, resolved_by=principal.username)
    elif target == "CLOSED": values.update(closed_at=now, closed_by=principal.username)
    await db.execute(update(Alert).where(Alert.id == alert_id).values(**values))
    await db.execute(text("INSERT INTO alert_audit_log(alert_id, actor, action, from_status, to_status, reason) VALUES (:id,:actor,'STATUS_CHANGE',:frm,:to,:reason)"),
                     {"id": str(alert_id), "actor": principal.username, "frm": current, "to": target, "reason": reason})
    await db.commit()
    return {"status": target, "alert_id": str(alert_id), "actor": principal.username, "idempotent": False}

@router.post("/{alert_id}/acknowledge")
async def acknowledge(alert_id: uuid.UUID, principal: Principal = Depends(require_role("OPERATOR")), db: AsyncSession = Depends(get_db)):
    return await _transition(alert_id, "ACKNOWLEDGED", principal, db)

@router.post("/{alert_id}/transition")
async def transition_alert(alert_id: uuid.UUID, target_status: str = Query(..., min_length=3, max_length=32), reason: Optional[str] = Query(None, max_length=1000),
                          principal: Principal = Depends(require_role("OPERATOR")), db: AsyncSession = Depends(get_db)):
    return await _transition(alert_id, target_status, principal, db, reason)

@router.get("/stats/counts")
async def alert_counts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE priority = 'HIGH') AS high,
               COUNT(*) FILTER (WHERE priority = 'MEDIUM') AS medium,
               COUNT(*) FILTER (WHERE priority = 'LOW') AS low,
               COUNT(*) FILTER (WHERE status = 'NEW') AS new,
               COUNT(*) FILTER (WHERE status = 'INVESTIGATING') AS investigating,
               COUNT(*) FILTER (WHERE status = 'RESOLVED') AS resolved,
               COUNT(*) FILTER (WHERE acknowledged = FALSE) AS unacknowledged,
               COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') AS last_hour
        FROM alerts"""))
    return dict(result.mappings().one())
