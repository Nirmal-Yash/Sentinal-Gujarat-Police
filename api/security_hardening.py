from __future__ import annotations

import os
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


DEFAULT_REQUEST_LIMIT = int(os.getenv("DEFAULT_REQUEST_LIMIT", str(10 * 1024 * 1024)))
SIZE_LIMITS = {
    "/api/test": int(os.getenv("TEST_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024))),
    "/api/evidence": int(os.getenv("EVIDENCE_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
}


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        raw = request.headers.get("content-length")
        if raw:
            try:
                size = int(raw)
            except ValueError:
                raise HTTPException(400, "Invalid Content-Length")
            limit = next((v for k, v in SIZE_LIMITS.items() if request.url.path.startswith(k)), DEFAULT_REQUEST_LIMIT)
            if size > limit:
                raise HTTPException(413, f"Request too large. Maximum: {limit // 1024 // 1024} MB")
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=()")
        response.headers.setdefault("Cache-Control", "no-store")
        if request.url.scheme == "https" or os.getenv("FORCE_SECURITY_HEADERS", "false").lower() == "true":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        csp = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' ws: wss:; "
            "worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        # Starlette's MutableHeaders supports item deletion, but not dict.pop().
        # Using del keeps the security-header middleware compatible with current
        # Starlette releases and prevents /health from becoming a 500 response.
        for header_name in ("Server", "X-Powered-By"):
            if header_name in response.headers:
                del response.headers[header_name]
        return response


def csrf_token_from_cookie(cookie_value: str | None) -> str | None:
    return cookie_value if cookie_value and len(cookie_value) >= 32 else None


def verify_cookie_csrf(request: Request, csrf_cookie: str | None) -> None:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    if not request.cookies.get("sentinel_session"):
        return
    if request.headers.get("Authorization", "").startswith("Bearer "):
        return
    if not csrf_cookie or csrf_cookie != request.headers.get("X-CSRF-Token"):
        raise HTTPException(403, "CSRF validation failed")
