"""Authenticated CCTV HLS proxy for cctv.corp8.cloud.

The browser calls this same-origin route. The API owns the provider session
and rewrites HLS resource references so segments/keys remain authenticated.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from auth import require_authenticated
from services.cctv_gateway import get_cctv_gateway

router = APIRouter(
    prefix="/cctv",
    tags=["cctv"],
    dependencies=[Depends(require_authenticated)],
)


_URI_ATTR = re.compile(r'URI="([^"]+)"')


def _proxy_url(asset_path: str) -> str:
    return "/api/cctv/" + asset_path.lstrip("/")


def _rewrite_manifest(body: str, manifest_path: str) -> str:
    """Rewrite HLS URI lines and URI= attributes to the local authenticated proxy."""
    base_dir = manifest_path.rsplit("/", 1)[0] + "/"

    def rewrite_uri(value: str) -> str:
        value = value.strip()
        if not value or value.startswith("#"):
            return value

        absolute = urlparse(value)
        if absolute.scheme in {"http", "https"}:
            path = absolute.path.lstrip("/")
            query = f"?{absolute.query}" if absolute.query else ""
            return _proxy_url(path + query)

        resolved = urljoin("/" + base_dir, value).lstrip("/")
        return _proxy_url(resolved)

    output: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            line = rewrite_uri(line)
        else:
            line = _URI_ATTR.sub(
                lambda match: f'URI="{rewrite_uri(match.group(1))}"',
                line,
            )
        output.append(line)

    return "\n".join(output) + ("\n" if body.endswith("\n") else "")


@router.get("/{asset_path:path}")
def proxy_cctv_asset(asset_path: str):
    """Proxy the current CCTV HLS manifest/segment/key using the server-side session."""
    if not re.fullmatch(r"cam\d{2}/.+", asset_path, re.IGNORECASE):
        raise HTTPException(400, "Invalid CCTV asset path")

    gateway = get_cctv_gateway()
    if not gateway.configured:
        raise HTTPException(503, "CCTV_PASSWORD is not configured on the server")

    try:
        upstream = gateway.proxy_asset(asset_path)
    except Exception as exc:
        raise HTTPException(502, f"CCTV upstream request failed: {exc}") from exc

    if upstream.status_code != 200:
        location = upstream.headers.get("Location")
        upstream.close()
        if upstream.status_code in {401, 403, 302, 303}:
            raise HTTPException(502, "CCTV authentication was rejected by the upstream gateway")
        raise HTTPException(502, f"CCTV upstream returned HTTP {upstream.status_code}", headers={"X-CCTV-Upstream-Status": str(upstream.status_code), **({"Location": location} if location else {})})

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")

    if asset_path.lower().endswith(".m3u8") or "mpegurl" in content_type.lower():
        try:
            body = upstream.content.decode("utf-8", errors="replace")
        finally:
            upstream.close()

        if not body.lstrip().startswith("#EXTM3U"):
            raise HTTPException(502, "CCTV upstream returned non-HLS content for a manifest")

        return Response(
            _rewrite_manifest(body, asset_path),
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
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
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
