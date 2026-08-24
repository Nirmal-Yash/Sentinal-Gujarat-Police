from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from models import Alert, AlertOut
from database import get_db
from typing import Optional
import uuid

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/", response_model=list[AlertOut])
async def list_alerts(
    priority:   Optional[str] = None,
    alert_type: Optional[str] = None,
    cam_id:     Optional[uuid.UUID] = None,
    unacked:    bool = False,
    limit:      int  = Query(50, le=200),
    offset:     int  = 0,
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
        q = q.where(Alert.acknowledged == False)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/{alert_id}/acknowledge")
async def acknowledge(alert_id: uuid.UUID, operator: str = "operator",
                       db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone
    await db.execute(
        update(Alert)
        .where(Alert.id == alert_id)
        .values(acknowledged=True,
                acknowledged_at=datetime.now(timezone.utc),
                acknowledged_by=operator)
    )
    await db.commit()
    return {"status": "acknowledged"}


@router.get("/stats/counts")
async def alert_counts(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    result = await db.execute(text("""
        SELECT
          COUNT(*)                                          AS total,
          COUNT(*) FILTER (WHERE priority = 'HIGH')        AS high,
          COUNT(*) FILTER (WHERE priority = 'MEDIUM')      AS medium,
          COUNT(*) FILTER (WHERE priority = 'LOW')         AS low,
          COUNT(*) FILTER (WHERE acknowledged = FALSE)     AS unacknowledged,
          COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') AS last_hour
        FROM alerts
    """))
    return dict(result.mappings().one())
