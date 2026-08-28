from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from models import Alert, AlertOut
from auth import require_authenticated, require_role, Principal
from database import get_db
from typing import Optional
import uuid

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(require_authenticated)])


@router.get("/", response_model=list[AlertOut])
async def list_alerts(
    priority: Optional[str] = None,
    alert_type: Optional[str] = None,
    cam_id: Optional[uuid.UUID] = None,
    unacked: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(Alert).order_by(desc(Alert.created_at)).limit(limit).offset(offset)
    if priority:
        q = q.where(Alert.priority == priority.upper())
    if alert_type:
        q = q.where(Alert.alert_type.ilike(f"%{alert_type}%"))
    if cam_id:
        q = q.where(Alert.cam_id == cam_id)
    if unacked:
        q = q.where(Alert.acknowledged.is_(False))
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/{alert_id}/acknowledge")
async def acknowledge(
    alert_id: uuid.UUID,
    principal: Principal = Depends(require_role("OPERATOR")),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge an alert using the authenticated actor, never caller-supplied identity."""
    from datetime import datetime, timezone
    result = await db.execute(
        update(Alert)
        .where(Alert.id == alert_id, Alert.acknowledged.is_(False))
        .values(
            acknowledged=True,
            acknowledged_at=datetime.now(timezone.utc),
            acknowledged_by=principal.username,
        )
        .returning(Alert.id)
    )
    if result.scalar_one_or_none() is None:
        exists = await db.execute(select(Alert.id).where(Alert.id == alert_id))
        if exists.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"status": "already_acknowledged", "alert_id": str(alert_id)}
    await db.commit()
    return {"status": "acknowledged", "alert_id": str(alert_id), "acknowledged_by": principal.username}


@router.get("/stats/counts")
async def alert_counts(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    result = await db.execute(text("""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE priority = 'HIGH') AS high,
          COUNT(*) FILTER (WHERE priority = 'MEDIUM') AS medium,
          COUNT(*) FILTER (WHERE priority = 'LOW') AS low,
          COUNT(*) FILTER (WHERE acknowledged = FALSE) AS unacknowledged,
          COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') AS last_hour
        FROM alerts
    """))
    return dict(result.mappings().one())
