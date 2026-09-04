"""Centralized security controls that wrap Sentinel business logic without changing it."""
from __future__ import annotations

import base64
import hashlib
import html
import hmac
import ipaddress
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

INSECURE_VALUES = {"", "change-me", "changeme", "sentinel-change-in-production", "replace-me", "replace-with-long-random-secret", "ci-only-sentinel-signing-secret", "ci-only-snapshot-signing-secret"}
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(x) for x in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
    "169.254.0.0/16", "100.64.0.0/10", "::1/128", "fc00::/7", "fe80::/10",
))
ALLOWED_EXTERNAL_HOSTS = {h.strip().lower() for h in os.getenv(
    "ALLOWED_EXTERNAL_HOSTS", "cctv.corp8.cloud,stream.corp8.cloud,103.250.160.189"
).split(",") if h.strip()}


def is_private_address(host: str) -> bool:
    try:
        return any(ipaddress.ip_address(host) in network for network in PRIVATE_NETWORKS)
    except ValueError:
        return False


def validate_external_url(url: str, *, allow_schemes: set[str]) -> str:
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError("Invalid URL format") from exc
    if parsed.scheme.lower() not in allow_schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not permitted")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("URL has no hostname")
    if host in ALLOWED_EXTERNAL_HOSTS:
        return url
    if is_private_address(host):
        raise ValueError("URL resolves to a private address")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 554), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Hostname could not be resolved") from exc
    for info in infos:
        resolved = info[4][0]
        if is_private_address(resolved):
            raise ValueError("URL resolves to a private address")
    raise ValueError("URL host is not on the permitted list")


def validate_rtsp_url(url: str) -> str:
    return validate_external_url(url.strip(), allow_schemes={"rtsp", "rtsps"})


def validate_hls_url(url: str) -> str:
    return validate_external_url(url.strip(), allow_schemes={"https"})


COMMON_PASSWORDS = {"password123", "sentinel123", "admin123", "gujarat2024", "police123", "123456789", "qwerty123", "letmein123"}
PASSWORD_RE = re.compile(r"[!@#$%^&*()\-_=+\[\]{}|;:,.<>?]")


def enforce_password_policy(password: str, username: str = "") -> None:
    errors: list[str] = []
    if len(password) < 12: errors.append("Minimum 12 characters required")
    if len(password) > 128: errors.append("Maximum 128 characters allowed")
    if not re.search(r"[A-Z]", password): errors.append("At least one uppercase letter required")
    if not re.search(r"[a-z]", password): errors.append("At least one lowercase letter required")
    if not re.search(r"\d", password): errors.append("At least one digit required")
    if not PASSWORD_RE.search(password): errors.append("At least one special character required")
    if username and username.lower() in password.lower(): errors.append("Password must not contain your username")
    if password.lower() in COMMON_PASSWORDS: errors.append("Password is too common")
    if len(set(password)) < 6: errors.append("Password is too repetitive")
    if errors:
        raise HTTPException(status_code=422, detail={"code": "PASSWORD_POLICY", "errors": errors})


def sanitise_text(value: str | None, max_length: int = 2000) -> str:
    if value is None:
        return ""
    return html.escape(re.sub(r"\s+", " ", value.strip()))[:max_length]


def validate_search_query(value: str, max_length: int = 100) -> str:
    value = value.strip()
    if len(value) > max_length:
        raise ValueError(f"Search query too long (max {max_length} characters)")
    return re.sub(r"[;'\"/\\]", "", value)


SIZE_LIMITS = {
    "/search/person/": 10 * 1024 * 1024,
    "/test/feeds/upload": 200 * 1024 * 1024,
    "/camera-imports/": 5 * 1024 * 1024,
    "/watchlist/": 10 * 1024 * 1024,
}
DEFAULT_REQUEST_LIMIT = 1 * 1024 * 1024


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        raw = request.headers.get("content-length")
        if raw:
            try:
                size = int(raw)
            except ValueError:
                raise HTTPException(400, "Invalid Content-Length")
            path = request.url.path.removeprefix("/api")
            limit = next((v for k, v in SIZE_LIMITS.items() if path.startswith(k)), DEFAULT_REQUEST_LIMIT)
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
    header = request.headers.get("X-CSRF-Token")
    if not header or not csrf_cookie or not hmac.compare_digest(header, csrf_cookie):
        raise HTTPException(status_code=403, detail="CSRF token required")


def fernet_from_secret(key: str | None) -> Fernet | None:
    """Build a Fernet instance from current or legacy deployment key material."""
    key = (key or "").strip()
    if not key:
        return None
    if key.lower() in INSECURE_VALUES:
        raise ValueError("FIELD_ENCRYPTION_KEY must not be a placeholder")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        if len(key) < 32:
            raise ValueError("FIELD_ENCRYPTION_KEY must be a Fernet key or a 32+ character secret") from exc
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


class FieldEncryption:
    """Application-level encryption for sensitive non-indexed fields/artifacts."""
    def __init__(self) -> None:
        self._fernet = None
        key = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()
        if key:
            # Older local deployments used a longer URL-safe secret. Keep
            # those installations readable without changing configured values.
            self._fernet = fernet_from_secret(key)

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def encrypt_bytes(self, data: bytes) -> bytes:
        if not self._fernet:
            raise RuntimeError("FIELD_ENCRYPTION_KEY is not configured")
        return self._fernet.encrypt(data)

    def decrypt_bytes(self, data: bytes) -> bytes:
        if not self._fernet:
            raise RuntimeError("FIELD_ENCRYPTION_KEY is not configured")
        try:
            return self._fernet.decrypt(data)
        except InvalidToken as exc:
            raise ValueError("Encrypted data could not be decrypted") from exc

    def encrypt_text(self, value: str) -> str:
        return base64.b64encode(self.encrypt_bytes(value.encode())).decode()

    def decrypt_text(self, value: str) -> str:
        return self.decrypt_bytes(base64.b64decode(value)).decode()

field_encryption = FieldEncryption()


def redact(value: object) -> str:
    text = str(value)
    secret_values = [os.getenv("CCTV_EMAIL", ""), os.getenv("CCTV_PASSWORD", ""), os.getenv("SECRET_KEY", ""), os.getenv("SNAPSHOT_TOKEN_SECRET", ""), os.getenv("JWT_REFRESH_SECRET_KEY", "")]
    for secret in secret_values:
        if secret and secret not in INSECURE_VALUES:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"Bearer\s+[A-Za-z0-9._-]{20,}", "Bearer [REDACTED]", text)
    text = re.sub(r"(?:password|access_token|refresh_token|embedding)=([^&\s]+)", r"\1=[REDACTED]", text, flags=re.I)
    return text


def secure_storage_path(root: str | Path, relative_key: str) -> Path:
    root_path = Path(root).resolve()
    candidate = (root_path / relative_key).resolve()
    if candidate != root_path and root_path not in candidate.parents:
        raise ValueError("Storage path escapes storage root")
    return candidate


def secure_random_secret(min_bytes: int = 32) -> str:
    return hashlib.sha256(os.urandom(max(32, min_bytes))).hexdigest()
