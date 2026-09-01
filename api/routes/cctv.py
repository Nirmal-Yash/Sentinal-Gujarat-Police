"""Authenticated CCTV HLS proxy for cctv.corp8.cloud."""
from __future__ import annotations

import os
import re
import time
from urllib.parse import urljoin, urlparse

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from auth import Principal, require_authenticated
from database import get_db
from services.cctv_gateway import get_cctv_gateway

router = APIRouter(prefix="/cctv", tags=["cctv"])
_URI_ATTR = re.compile(r'URI="([^"]+)"')
_SECRET_PLACEHOLDERS = {"", "change-me", "changeme", "sentinel-change-in-production", "replace-me", "replace-with-long-random-secret"}
_CAMERA_RE = re.compile(r"cam(\d{2})", re.IGNORECASE)


def _secret() -> str:
    secret = (os.getenv("SECRET_KEY", "") or "").strip()
    if secret.lower() in _SECRET_PLACEHOLDERS:
        raise HTTPException(503, "Playback signing secret is not configured")
    return secret


def _verify_playback_token(token: str, camera_id: str) -> None:
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired CCTV playback token") from exc
    if claims.get("sub") != "cctv-hls" or str(claims.get("camera", "")).lower() != camera_id.lower():
        raise HTTPException(403, "CCTV playback token is not valid for this camera")


def _camera_id(value: str | int) -> str:
    text_value = str(value).strip()
    match = _CAMERA_RE.fullmatch(text_value)
    if match:
        return f"cam{int(match.group(1)):02d}"
    if text_value.isdigit():
        return f"cam{int(text_value):02d}"
    raise HTTPException(400, "Invalid CCTV camera identifier")


def _proxy_url(asset_path: str, token: str) -> str:
    separator = "&" if "?" in asset_path else "?"
    return "/api/cctv/" + asset_path.lstrip("/") + separator + "access_token=" + token


def _rewrite_manifest(body: str, manifest_path: str, token: str) -> str:
    base_dir = "/" + manifest_path.rsplit("/", 1)[0].strip("/") + "/"

    def rewrite_uri(value: str) -> str:
        value = value.strip()
        if not value or value.startswith("#"):
            return value
        absolute = urlparse(value)
        if absolute.scheme in {"http", "https"}:
            path = absolute.path.lstrip("/")
            query = f"?{absolute.query}" if absolute.query else ""
            return _proxy_url(path + query, token)
        resolved = urljoin(base_dir, value).lstrip("/")
        return _proxy_url(resolved, token)

    output: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            line = rewrite_uri(line)
        else:
            line = _URI_ATTR.sub(lambda m: f'URI="{rewrite_uri(m.group(1))}"', line)
        output.append(line)
    return "\n".join(output) + ("\n" if body.endswith("\n") else "")


@router.get("/token/{camera_ref}")
async def issue_playback_token(
    camera_ref: str,
    _: Principal = Depends(require_authenticated),
    db: AsyncSession = Depends(get_db),
):
    """Issue a short-lived token for one registered camera's HLS assets."""
    camera_id = _camera_id(camera_ref)
    number = int(camera_id[3:])
    exists = await db.scalar(
        text("SELECT 1 FROM cameras WHERE stream_id=:stream_id AND status <> 'deleted'"),
        {"stream_id": number},
    )
    if not exists:
        raise HTTPException(404, f"Camera {camera_id} is not registered")
    expires_at = int(time.time()) + 300
    token = jwt.encode(
        {"sub": "cctv-hls", "camera": camera_id, "exp": expires_at},
        _secret(),
        algorithm="HS256",
    )
    return {"token": token, "expires_at": expires_at, "ttl_seconds": 300, "camera": camera_id}


@router.get("/{asset_path:path}")
def proxy_cctv_asset(asset_path: str, access_token: str = Query(..., min_length=1)):
    match = re.fullmatch(r"(cam\d{2})/(.+)", asset_path, re.IGNORECASE)
    if not match:
        raise HTTPException(400, "Invalid CCTV asset path")
    camera_id = _camera_id(match.group(1))
    _verify_playback_token(access_token, camera_id)

    gateway = get_cctv_gateway()
    if not gateway.configured:
        raise HTTPException(503, "CCTV_PASSWORD is not configured on the server")
    try:
        upstream = gateway.proxy_asset(asset_path)
    except Exception as exc:
        raise HTTPException(502, f"CCTV upstream request failed: {exc}") from exc

    if upstream.status_code != 200:
        status = upstream.status_code
        upstream.close()
        if status in {401, 403, 302, 303}:
            raise HTTPException(502, "CCTV authentication was rejected by the upstream gateway")
        raise HTTPException(502, f"CCTV upstream returned HTTP {status}")

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    if asset_path.lower().endswith(".m3u8") or "mpegurl" in content_type.lower():
        try:
            body = upstream.content.decode("utf-8", errors="replace")
        finally:
            upstream.close()
        if not body.lstrip().startswith("#EXTM3U"):
            raise HTTPException(502, "CCTV upstream returned non-HLS content for a manifest")
        return Response(
            _rewrite_manifest(body, asset_path, access_token),
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Access-Control-Allow-Origin": "*"},
        )

    def iterator():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    safe_type = content_type.split(";", 1)[0].strip() or "application/octet-stream"
    return StreamingResponse(
        iterator(),
        media_type=safe_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Access-Control-Allow-Origin": "*"},
    )
