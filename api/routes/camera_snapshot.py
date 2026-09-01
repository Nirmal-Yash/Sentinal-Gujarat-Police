from __future__ import annotations

import base64
import os
import uuid

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from auth import Principal, require_authenticated
from database import get_db
from signed_asset_tokens import issue_asset_token, verify_asset_token

router = APIRouter(prefix="/cameras", tags=["camera-assets"])
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SNAPSHOT_TOKEN_SECRET_ENV = "SNAPSHOT_TOKEN_SECRET"


async def _camera(db: AsyncSession, camera_id: uuid.UUID):
    row = (await db.execute(
        text("SELECT id, external_id, stream_id, status FROM cameras WHERE id=CAST(:id AS uuid)"),
        {"id": str(camera_id)},
    )).mappings().first()
    if not row or row["status"] == "deleted":
        raise HTTPException(404, "Camera not found")
    return row


def _provider_id(row) -> str:
    external = str(row.get("external_id") or "").strip().lower()
    if external.startswith("cam") and len(external) == 5 and external[3:].isdigit():
        return external
    stream_id = row.get("stream_id")
    if stream_id is None:
        raise HTTPException(422, "Camera has no provider playback identifier")
    return f"cam{int(stream_id):02d}"


@router.get("/{cam_id}/snapshot-token")
async def snapshot_token(
    cam_id: uuid.UUID,
    principal: Principal = Depends(require_authenticated),
    db: AsyncSession = Depends(get_db),
):
    row = await _camera(db, cam_id)
    provider_id = _provider_id(row)
    try:
        token = issue_asset_token(
            kind="snapshot",
            resource=provider_id,
            env_name=SNAPSHOT_TOKEN_SECRET_ENV,
            ttl_seconds=int(os.getenv("SNAPSHOT_TOKEN_TTL_SECS", "120")),
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"camera_id": str(cam_id), "provider_id": provider_id, "token": token, "expires_in": int(os.getenv("SNAPSHOT_TOKEN_TTL_SECS", "120"))}


@router.get("/{cam_id}/snapshot")
async def snapshot(
    cam_id: uuid.UUID,
    access_token: str | None = Query(None, min_length=1),
    principal: Principal | None = Depends(require_authenticated),
    db: AsyncSession = Depends(get_db),
):
    # Signed token is intended for browser media elements. Normal API callers
    # may continue using the authenticated Sentinel session.
    row = await _camera(db, cam_id)
    provider_id = _provider_id(row)
    if access_token:
        try:
            verify_asset_token(
                token=access_token,
                kind="snapshot",
                resource=provider_id,
                env_name=SNAPSHOT_TOKEN_SECRET_ENV,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(401, "Invalid or expired snapshot token") from exc
    elif principal is None:
        raise HTTPException(401, "Authentication required")

    client = redis_lib.from_url(REDIS_URL, decode_responses=False)
    try:
        data = client.get(f"snapshot:{cam_id}")
    finally:
        try:
            client.close()
        except Exception:
            pass
    if not data:
        raise HTTPException(404, "No snapshot available yet — stream may still be connecting")
    try:
        payload = base64.b64decode(data, validate=True)
    except Exception as exc:
        raise HTTPException(502, "Stored snapshot data is invalid") from exc
    return Response(content=payload, media_type="image/jpeg", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
