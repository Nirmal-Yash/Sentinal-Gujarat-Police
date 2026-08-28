from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import re, uuid, json, os
from pathlib import Path
from auth import Principal, require_permission
from database import get_db

router = APIRouter(prefix="/evidence", tags=["evidence"])
EVIDENCE_ROOT = Path(os.getenv("EVIDENCE_ROOT", "/evidence")).resolve()

class EvidenceCreate(BaseModel):
    event_id: str | None = Field(None, max_length=255)
    alert_id: uuid.UUID | None = None
    camera_id: uuid.UUID | None = None
    captured_at: str | None = None
    media_type: str = Field(min_length=1, max_length=64)
    storage_key: str = Field(min_length=1, max_length=2048)
    sha256: str | None = Field(None, min_length=64, max_length=64)
    metadata: dict = Field(default_factory=dict)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value):
        if value is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        return value

    @field_validator("storage_key")
    @classmethod
    def validate_storage_key(cls, value):
        if value.strip() != value or ".." in value or value.startswith(("/", "\\")):
            raise ValueError("storage_key must be an opaque relative object key")
        return value

@router.get("/")
async def list_evidence(alert_id: uuid.UUID | None = None, event_id: str | None = Query(None, max_length=255), limit: int = Query(50, ge=1, le=200), _: Principal = Depends(require_permission("evidence:read")), db: AsyncSession = Depends(get_db)):
    conditions, params = ["1=1"], {"limit": limit}
    if alert_id:
        conditions.append("alert_id=:alert_id"); params["alert_id"] = str(alert_id)
    if event_id:
        conditions.append("event_id=:event_id"); params["event_id"] = event_id
    result = await db.execute(text(f"SELECT id,event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata,created_at FROM evidence WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT :limit"), params)
    return [dict(row) for row in result.mappings()]

@router.post("/", status_code=201)
async def create_evidence(body: EvidenceCreate, principal: Principal = Depends(require_permission("evidence:create")), db: AsyncSession = Depends(get_db)):
    if body.alert_id and not await db.scalar(text("SELECT 1 FROM alerts WHERE id=CAST(:id AS uuid)"), {"id": str(body.alert_id)}):
        raise HTTPException(422, "alert_id does not reference an existing alert")
    if body.camera_id and not await db.scalar(text("SELECT 1 FROM cameras WHERE id=CAST(:id AS uuid) AND status <> 'deleted'"), {"id": str(body.camera_id)}):
        raise HTTPException(422, "camera_id does not reference an active camera")
    values = {"event_id": body.event_id, "alert_id": str(body.alert_id) if body.alert_id else None, "camera_id": str(body.camera_id) if body.camera_id else None, "captured_at": body.captured_at, "media_type": body.media_type, "storage_key": body.storage_key, "sha256": body.sha256, "metadata": json.dumps({**body.metadata, "created_by": principal.username})}
    row = (await db.execute(text("""INSERT INTO evidence(event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata)
        VALUES(:event_id,CAST(:alert_id AS uuid),CAST(:camera_id AS uuid),CAST(:captured_at AS timestamptz),:media_type,:storage_key,:sha256,CAST(:metadata AS jsonb))
        RETURNING id,event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata,created_at"""), values)).mappings().one()
    await db.execute(text("""INSERT INTO evidence_audit_log(evidence_id,actor,action,details)
        VALUES(CAST(:id AS uuid),:actor,'CREATE',CAST(:details AS jsonb))"""), {"id": str(row["id"]), "actor": principal.username, "details": json.dumps({"event_id": body.event_id, "alert_id": str(body.alert_id) if body.alert_id else None, "camera_id": str(body.camera_id) if body.camera_id else None})})
    await db.commit()
    return dict(row)

@router.get("/{evidence_id}")
async def get_evidence(evidence_id: uuid.UUID, _: Principal = Depends(require_permission("evidence:read")), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(text("SELECT id,event_id,alert_id,camera_id,captured_at,media_type,storage_key,sha256,metadata,created_at FROM evidence WHERE id=CAST(:id AS uuid)"), {"id": str(evidence_id)})).mappings().first()
    if not row:
        raise HTTPException(404, "Evidence not found")
    return dict(row)

@router.get("/{evidence_id}/content")
async def get_evidence_content(evidence_id: uuid.UUID, _: Principal = Depends(require_permission("evidence:read")), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(text("SELECT storage_key,media_type,sha256 FROM evidence WHERE id=CAST(:id AS uuid)"), {"id": str(evidence_id)})).mappings().first()
    if not row:
        raise HTTPException(404, "Evidence not found")
    target = (EVIDENCE_ROOT / row["storage_key"]).resolve()
    try:
        target.relative_to(EVIDENCE_ROOT)
    except ValueError as exc:
        raise HTTPException(400, "Invalid evidence storage reference") from exc
    if not target.is_file():
        raise HTTPException(404, "Evidence content is unavailable")
    return FileResponse(target, media_type=row["media_type"], headers={"X-Evidence-SHA256": row["sha256"] or ""})
