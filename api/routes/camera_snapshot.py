from __future__ import annotations

import base64
import os
import uuid

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from auth import COOKIE_NAME, Principal, current_principal, require_authenticated, principal_from_token
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
    _: Principal = Depends(require_authenticated),
    db: AsyncSession = Depends(get_db),
):
    row = await _camera(db, cam_id)
    provider_id = _provider_id(row)
    try:
        ttl = int(os.getenv("SNAPSHOT_TOKEN_TTL_SECS", "120"))
        token = issue_asset_token(kind="snapshot", resource=provider_id, env_name=SNAPSHOT_TOKEN_SECRET_ENV, ttl_seconds=ttl)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"camera_id": str(cam_id), "provider_id": provider_id, "token": token, "expires_in": ttl}


@router.get("/{cam_id}/snapshot")
async def snapshot(
    cam_id: uuid.UUID,
    request: Request,
    access_token: str | None = Query(None, min_length=1),
    signed_token: str | None = Query(None, alias="st", min_length=1),
    db: AsyncSession = Depends(get_db),
):
    token = access_token or signed_token
    row = await _camera(db, cam_id)
    provider_id = _provider_id(row)
    if token:
        try:
            verify_asset_token(token=token, kind="snapshot", resource=provider_id, env_name=SNAPSHOT_TOKEN_SECRET_ENV)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(401, "Invalid or expired snapshot token") from exc
    else:
        session_token = request.cookies.get(COOKIE_NAME)
        if not session_token:
            raise HTTPException(401, "Snapshot authentication required")
        await principal_from_token(session_token, db)

    client = redis_lib.from_url(REDIS_URL, decode_responses=False)
    try:
        data = client.get(f"snapshot:{cam_id}")
        if not data:
            # Ingestion writes the UUID key, but a short restart window can
            # leave only the provider alias.  Read that alias before reporting
            # a false unavailable state.
            data = client.get(f"snapshot:{provider_id}")
        if not data:
            # Last-resort recovery for frames already accepted into the stream
            # when the separate snapshot key expired between requests.
            for _, fields in client.xrevrange("raw_frames", count=200):
                value = fields.get(b"cam_id") or fields.get("cam_id")
                value_text = value.decode(errors="ignore") if isinstance(value, bytes) else str(value or "")
                if value_text == str(cam_id):
                    data = fields.get(b"frame") or fields.get("frame")
                    if data:
                        break
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
