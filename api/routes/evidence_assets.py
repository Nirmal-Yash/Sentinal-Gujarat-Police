from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import Session
from signed_asset_tokens import issue_asset_token, verify_asset_token

router = APIRouter(prefix="/evidence", tags=["evidence-assets"])
EVIDENCE_ROOT = Path(os.getenv("EVIDENCE_STORAGE_PATH", "/evidence")).resolve()
EVIDENCE_TOKEN_ENV = "SNAPSHOT_TOKEN_SECRET"


async def _get_evidence(evidence_id: uuid.UUID):
    async with Session() as db:
        row = (await db.execute(
            text("SELECT id, storage_key, media_type, sha256 FROM evidence WHERE id=CAST(:id AS uuid)"),
            {"id": str(evidence_id)},
        )).mappings().first()
    if not row:
        raise HTTPException(404, "Evidence not found")
    return row


@router.get("/{evidence_id}/signed-token")
async def evidence_signed_token(evidence_id: uuid.UUID):
    row = await _get_evidence(evidence_id)
    try:
        ttl = int(os.getenv("EVIDENCE_TOKEN_TTL_SECS", "300"))
        token = issue_asset_token(kind="evidence", resource=str(evidence_id), env_name=EVIDENCE_TOKEN_ENV, ttl_seconds=ttl)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"evidence_id": str(evidence_id), "token": token, "expires_in": ttl, "sha256": row["sha256"]}


@router.get("/{evidence_id}/content-signed")
async def evidence_content_signed(evidence_id: uuid.UUID, access_token: str = Query(..., min_length=1)):
    try:
        verify_asset_token(token=access_token, kind="evidence", resource=str(evidence_id), env_name=EVIDENCE_TOKEN_ENV)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(401, "Invalid or expired evidence token") from exc
    row = await _get_evidence(evidence_id)
    target = (EVIDENCE_ROOT / row["storage_key"]).resolve()
    try:
        target.relative_to(EVIDENCE_ROOT)
    except ValueError as exc:
        raise HTTPException(400, "Invalid evidence storage reference") from exc
    if not target.is_file():
        raise HTTPException(404, "Evidence content is unavailable")
    return FileResponse(
        target,
        media_type=row["media_type"],
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Evidence-SHA256": row["sha256"] or "",
            "X-Content-Type-Options": "nosniff",
        },
    )
