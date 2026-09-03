from __future__ import annotations
import os, uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text
from auth import Principal, require_permission
from database import Session
from signed_asset_tokens import issue_asset_token, verify_asset_token
from cryptography.fernet import InvalidToken
from security_hardening import fernet_from_secret

router = APIRouter(prefix="/evidence", tags=["evidence-assets"])
EVIDENCE_ROOT = Path(os.getenv("EVIDENCE_STORAGE_PATH", "/evidence")).resolve()
EVIDENCE_TOKEN_ENV = "SNAPSHOT_TOKEN_SECRET"
FIELD_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()
_FERNET = fernet_from_secret(FIELD_KEY)

async def _get_evidence(evidence_id: uuid.UUID):
    async with Session() as db:
        row=(await db.execute(text("SELECT id,storage_key,media_type,sha256 FROM evidence WHERE id=CAST(:id AS uuid)"),{"id":str(evidence_id)})).mappings().first()
    if not row: raise HTTPException(404,"Evidence not found")
    return row

@router.get("/{evidence_id}/signed-token")
async def evidence_signed_token(evidence_id: uuid.UUID, _: Principal = Depends(require_permission("evidence:read"))):
    row=await _get_evidence(evidence_id)
    try:
        ttl=int(os.getenv("EVIDENCE_TOKEN_TTL_SECS","300")); token=issue_asset_token(kind="evidence",resource=str(evidence_id),env_name=EVIDENCE_TOKEN_ENV,ttl_seconds=ttl)
    except RuntimeError as exc: raise HTTPException(503,str(exc)) from exc
    return {"evidence_id":str(evidence_id),"token":token,"expires_in":ttl,"sha256":row["sha256"]}

@router.get("/{evidence_id}/content-signed")
async def evidence_content_signed(evidence_id: uuid.UUID, access_token: str | None = Query(None, min_length=1), signed_token: str | None = Query(None, alias="st", min_length=1)):
    access_token = access_token or signed_token
    if not access_token:
        raise HTTPException(401, "Evidence token is required")
    try: verify_asset_token(token=access_token,kind="evidence",resource=str(evidence_id),env_name=EVIDENCE_TOKEN_ENV)
    except (RuntimeError,ValueError) as exc: raise HTTPException(401,"Invalid or expired evidence token") from exc
    row=await _get_evidence(evidence_id); target=(EVIDENCE_ROOT/row["storage_key"]).resolve()
    try: target.relative_to(EVIDENCE_ROOT)
    except ValueError as exc: raise HTTPException(400,"Invalid evidence storage reference") from exc
    if not target.is_file():
        encrypted=target.with_suffix(target.suffix+".enc")
        if _FERNET and encrypted.is_file():
            try: payload=_FERNET.decrypt(encrypted.read_bytes())
            except InvalidToken as exc: raise HTTPException(500,"Evidence decryption failed") from exc
            return Response(payload,media_type=row["media_type"],headers={"Cache-Control":"private, max-age=300","X-Evidence-SHA256":row["sha256"] or "","X-Content-Type-Options":"nosniff"})
        raise HTTPException(404,"Evidence content is unavailable")
    return Response(target.read_bytes(),media_type=row["media_type"],headers={"Cache-Control":"private, max-age=300","X-Evidence-SHA256":row["sha256"] or "","X-Content-Type-Options":"nosniff"})

@router.get("/{evidence_id}/thumbnail")
async def evidence_thumbnail(evidence_id: uuid.UUID, _: Principal = Depends(require_permission("evidence:read"))):
    async with Session() as db:
        row=(await db.execute(text("SELECT storage_key,metadata FROM evidence WHERE id=CAST(:id AS uuid)"),{"id":str(evidence_id)})).mappings().first()
    if not row: raise HTTPException(404,"Evidence not found")
    thumbnail_key=(row["metadata"] or {}).get("thumbnail_key")
    if not thumbnail_key: raise HTTPException(404,"Evidence thumbnail is unavailable")
    target=(EVIDENCE_ROOT/thumbnail_key).resolve()
    try: target.relative_to(EVIDENCE_ROOT)
    except ValueError as exc: raise HTTPException(400,"Invalid evidence thumbnail reference") from exc
    if target.is_file():
        return Response(target.read_bytes(),media_type="image/jpeg",headers={"Cache-Control":"private, max-age=300","X-Content-Type-Options":"nosniff"})
    encrypted=target.with_suffix(target.suffix+".enc")
    if _FERNET and encrypted.is_file():
        try: payload=_FERNET.decrypt(encrypted.read_bytes())
        except InvalidToken as exc: raise HTTPException(500,"Evidence thumbnail decryption failed") from exc
        return Response(payload,media_type="image/jpeg",headers={"Cache-Control":"private, max-age=300","X-Content-Type-Options":"nosniff"})
    raise HTTPException(404,"Evidence thumbnail is unavailable")
