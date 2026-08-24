from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import WatchlistEntry, WatchlistOut, WatchlistCreate
from database import get_db
import uuid

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("/", response_model=list[WatchlistOut])
async def list_watchlist(active_only: bool = True,
                          db: AsyncSession = Depends(get_db)):
    q = select(WatchlistEntry).order_by(WatchlistEntry.created_at.desc())
    if active_only:
        q = q.where(WatchlistEntry.is_active == True)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=WatchlistOut)
async def add_to_watchlist(body: WatchlistCreate,
                            db: AsyncSession = Depends(get_db)):
    entry = WatchlistEntry(
        name=body.name,
        entity_type=body.entity_type,
        description=body.description,
        plate_number=body.plate_number.upper().replace(" ", "") if body.plate_number else None,
        alert_priority=body.alert_priority.upper(),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
async def deactivate(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    entry = await db.get(WatchlistEntry, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    entry.is_active = False
    await db.commit()
    return {"status": "deactivated"}
