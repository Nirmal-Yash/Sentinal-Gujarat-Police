from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from models import WatchlistEntry, WatchlistOut, WatchlistCreate
from auth import require_authenticated, require_role, Principal
from database import get_db
import uuid
import re
import os, asyncio, time, json, base64
import numpy as np

router = APIRouter(prefix="/watchlist", tags=["watchlist"], dependencies=[Depends(require_authenticated)])


@router.get("/", response_model=list[WatchlistOut])
async def list_watchlist(active_only: bool = True, db: AsyncSession = Depends(get_db)):
    q = select(WatchlistEntry).order_by(WatchlistEntry.created_at.desc())
    if active_only:
        q = q.where(WatchlistEntry.is_active == True)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=WatchlistOut)
async def add_to_watchlist(body: WatchlistCreate, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    entry = WatchlistEntry(
        name=body.name,
        entity_type=body.entity_type,
        description=body.description,
        plate_number=re.sub(r"[^A-Z0-9]", "", body.plate_number.upper()) if body.plate_number else None,
        alert_priority=body.alert_priority.upper(),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.post("/person-photo", response_model=WatchlistOut, status_code=201)
async def add_person_photo_to_watchlist(
    name: str = Form(..., min_length=1, max_length=255),
    description: str = Form(""),
    alert_priority: str = Form("HIGH"),
    file: UploadFile = File(...),
    principal: Principal = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(415, "Upload an image file")
    payload = await file.read()
    if not payload or len(payload) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image must be between 1 byte and 10 MB")

    r = __import__("redis.asyncio", fromlist=["from_url"]).from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=False)
    request_id = uuid.uuid4().hex
    image_key = f"person:image:{request_id}"
    result_key = f"person:result:{request_id}"
    try:
        await r.set(image_key, payload, ex=30)
        await r.xadd("person:investigations", {"request_id": request_id, "image_key": image_key, "result_key": result_key}, maxlen=1000, approximate=True)
        deadline = time.monotonic() + float(os.getenv("PERSON_INVESTIGATION_TIMEOUT", "20"))
        result = None
        while time.monotonic() < deadline:
            raw = await r.get(result_key)
            if raw:
                result = json.loads(raw)
                break
            await asyncio.sleep(0.15)
        if not result or result.get("status") != "ok":
            raise HTTPException(422, "No usable face was detected in the uploaded photo")
        if int(result.get("face_count", 0)) != 1 or len(result.get("embeddings", [])) != 1:
            raise HTTPException(422, "Exactly one visible face is required for a person watchlist entry")
        embedding = np.frombuffer(base64.b64decode(result["embeddings"][0]), dtype=np.float32).copy()
        embedding /= np.linalg.norm(embedding) + 1e-9
        entry = WatchlistEntry(name=name.strip(), entity_type="person", description=description.strip(), plate_number=None, alert_priority=alert_priority.upper())
        db.add(entry)
        await db.flush()
        await db.execute(text("UPDATE watchlist SET embedding=CAST(:embedding AS vector) WHERE id=CAST(:id AS uuid)"), {"id": str(entry.id), "embedding": "[" + ",".join(str(float(x)) for x in embedding.tolist()) + "]"})
        await db.commit()
        await db.refresh(entry)
        return entry
    finally:
        try:
            await r.delete(image_key)
            await r.delete(result_key)
            await r.aclose()
        except Exception:
            pass


@router.delete("/{entry_id}")
async def deactivate(entry_id: uuid.UUID, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    entry = await db.get(WatchlistEntry, entry_id)
    if not entry:
        raise HTTPException(404, "Not found")
    entry.is_active = False
    await db.commit()
    return {"status": "deactivated"}
