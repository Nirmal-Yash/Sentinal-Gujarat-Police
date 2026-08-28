from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from auth import Principal, require_role
from database import get_db

router = APIRouter(prefix="/evidence", tags=["evidence"], dependencies=[Depends(require_role("VIEWER"))])

class EvidenceCreate(BaseModel):
    event_id: str | None = Field(None, max_length=255)
    alert_id: uuid.UUID | None = None
    camera_id: uuid.UUID | None = None
    captured_at: str | None = None
    media_type: str = Field(min_length=1, max_length=64)
    storage_key: str = Field(min_length=1, max_length=2048)
    sha256: str | None = Field(None, max_length=128)
    metadata: dict = Field(default_factory=dict)

@router.get("/")
async def list_evidence(alert_id: uuid.UUID | None = None, event_id: str | None = Query(None, max_length=255), limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)):
    conditions, params = ["1=1"], {"limit": limit}
    if alert_id:
        conditions.append("alert_id=:alert_id"); params["alert_id"] = str(alert_id)
    if event_id:
        conditions.append("event_id=:event_id"); params["event_id"] = event_id
    result = await db.execute(text(f"SELECT id,event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata,created_at FROM evidence WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT :limit"), params)
    return [dict(row) for row in result.mappings()]

@router.post("/", status_code=201)
async def create_evidence(body: EvidenceCreate, principal: Principal = Depends(require_role("OPERATOR")), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(text("""INSERT INTO evidence(event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata)
        VALUES(:event_id,CAST(:alert_id AS uuid),CAST(:camera_id AS uuid),CAST(:captured_at AS timestamptz),:media_type,:storage_key,:sha256,CAST(:metadata AS jsonb))
        RETURNING id,event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata,created_at"""), {
            "event_id": body.event_id, "alert_id": str(body.alert_id) if body.alert_id else None,
            "camera_id": str(body.camera_id) if body.camera_id else None, "captured_at": body.captured_at,
            "media_type": body.media_type, "storage_key": body.storage_key, "sha256": body.sha256,
            "metadata": __import__("json").dumps({**body.metadata, "created_by": principal.username})
        })).mappings().one()
    await db.commit()
    return dict(row)

@router.get("/{evidence_id}")
async def get_evidence(evidence_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(text("SELECT id,event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata,created_at FROM evidence WHERE id=CAST(:id AS uuid)"), {"id": str(evidence_id)})).mappings().first()
    if not row: raise HTTPException(404, "Evidence not found")
    return dict(row)
