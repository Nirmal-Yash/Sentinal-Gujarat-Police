"""JWT/RBAC boundary with short-lived access tokens and rotating refresh sessions."""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from security_hardening import enforce_password_policy

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "")
REFRESH_SECRET = os.getenv("JWT_REFRESH_SECRET_KEY", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = max(5, int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")))
REFRESH_TOKEN_HOURS = max(1, int(os.getenv("REFRESH_TOKEN_EXPIRE_HOURS", "8")))
security = HTTPBearer(auto_error=False)
ROLE_ORDER = {"VIEWER": 1, "OPERATOR": 2, "INVESTIGATOR": 2, "AUDITOR": 2, "ADMIN": 3, "SUPERADMIN": 4}
ROLE_PERMISSIONS = {
    "VIEWER": {"camera:read", "alert:read", "search:read", "evidence:read"},
    "OPERATOR": {"camera:read", "alert:read", "alert:operate", "search:read", "evidence:read", "evidence:create"},
    "INVESTIGATOR": {"camera:read", "alert:read", "alert:operate", "search:read", "report:read", "evidence:read", "evidence:create"},
    "AUDITOR": {"camera:read", "alert:read", "search:read", "report:read", "evidence:read", "audit:read"},
    "ADMIN": {"camera:read", "camera:write", "alert:read", "alert:operate", "search:read", "report:read", "evidence:read", "evidence:create", "registry:admin", "audit:read"},
    "SUPERADMIN": {"camera:read", "camera:write", "alert:read", "alert:operate", "search:read", "report:read", "evidence:read", "evidence:create", "registry:admin", "audit:read", "system:admin"},
}
COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "sentinel_session")
REFRESH_COOKIE_NAME = os.getenv("AUTH_REFRESH_COOKIE_NAME", "sentinel_refresh")
COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax").lower()
MAX_SESSIONS_PER_USER = max(1, int(os.getenv("MAX_SESSIONS_PER_USER", "3")))
LOCKOUT_USER_THRESHOLD = max(3, int(os.getenv("LOCKOUT_USER_THRESHOLD", "5")))
LOCKOUT_IP_THRESHOLD = max(10, int(os.getenv("LOCKOUT_IP_THRESHOLD", "20")))
LOCKOUT_WINDOW_MINUTES = max(1, int(os.getenv("LOCKOUT_WINDOW_MINUTES", "15")))
LOCKOUT_DURATION_MINUTES = max(1, int(os.getenv("LOCKOUT_DURATION_MINUTES", "30")))

@dataclass(frozen=True)
class Principal:
    user_id: str | None
    username: str
    role: str
    jti: str | None = None


def hash_password(value: str) -> str:
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()


def verify_password(value: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(value.encode(), stored.encode())
    except (ValueError, TypeError):
        return False


def _require_signing_secrets() -> None:
    if not SECRET_KEY or SECRET_KEY == "sentinel-change-in-production":
        raise HTTPException(503, "JWT signing secret is not configured")
    if not REFRESH_SECRET or REFRESH_SECRET == SECRET_KEY:
        raise HTTPException(503, "JWT refresh signing secret is not configured")


def issue_access_token(user_id: str, username: str, role: str, session_id: str) -> tuple[str, str, datetime]:
    _require_signing_secrets()
    expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    jti = str(uuid.uuid4())
    token = jwt.encode({"sub": user_id, "username": username, "role": role, "sid": session_id, "jti": jti, "exp": expires, "type": "access"}, SECRET_KEY, algorithm=ALGORITHM)
    return token, jti, expires


def issue_refresh_token(user_id: str, session_id: str) -> tuple[str, str, datetime]:
    _require_signing_secrets()
    expires = datetime.now(timezone.utc) + timedelta(hours=REFRESH_TOKEN_HOURS)
    jti = uuid.uuid4()
    token = jwt.encode({"sub": user_id, "sid": session_id, "jti": str(jti), "exp": expires, "type": "refresh"}, REFRESH_SECRET, algorithm=ALGORITHM)
    return token, str(jti), expires


async def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> Principal:
    if not AUTH_REQUIRED:
        return Principal(None, "local-development", "SUPERADMIN")
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else session_token
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")
    return await principal_from_token(token, db)


async def principal_from_token(token: str, db: AsyncSession) -> Principal:
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if claims.get("type", "access") != "access":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
        user_id, jti, role = claims["sub"], claims["jti"], claims["role"]
    except HTTPException:
        raise
    except (jwt.PyJWTError, KeyError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    row = (await db.execute(text("""SELECT u.username, u.role FROM users u JOIN user_sessions s ON s.user_id=u.id
        WHERE u.id=CAST(:uid AS uuid) AND s.jti=CAST(:jti AS uuid) AND u.is_active=TRUE
          AND s.revoked=FALSE AND s.expires_at > NOW()"""), {"uid": user_id, "jti": jti})).mappings().first()
    if not row or row["role"] != role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is no longer valid")
    return Principal(user_id, row["username"], row["role"], jti)


async def enforce_session_limit(user_id: str, db: AsyncSession) -> None:
    rows = (await db.execute(text("""SELECT id,jti,expires_at FROM user_sessions
        WHERE user_id=CAST(:uid AS uuid) AND revoked=FALSE AND expires_at > NOW()
        ORDER BY created_at ASC"""), {"uid": user_id})).mappings().all()
    if len(rows) < MAX_SESSIONS_PER_USER:
        return
    overflow = len(rows) - MAX_SESSIONS_PER_USER + 1
    for row in rows[:overflow]:
        await db.execute(text("UPDATE user_sessions SET revoked=TRUE WHERE id=CAST(:id AS uuid)"), {"id": str(row["id"])})


def _ip_hash(request: Request | None) -> str:
    address = request.client.host if request and request.client else "unknown"
    return hashlib.sha256(address.encode()).hexdigest()


async def is_locked(username: str, request: Request, db: AsyncSession) -> bool:
    window = f"{LOCKOUT_WINDOW_MINUTES} minutes"
    user_failures = await db.scalar(text("SELECT COUNT(*) FROM auth_attempts WHERE username=:username AND succeeded=FALSE AND created_at > NOW() - CAST(:window AS interval)"), {"username": username, "window": window})
    ip_failures = await db.scalar(text("SELECT COUNT(*) FROM auth_attempts WHERE ip_hash=:ip AND succeeded=FALSE AND created_at > NOW() - CAST(:window AS interval)"), {"ip": _ip_hash(request), "window": window})
    return int(user_failures or 0) >= LOCKOUT_USER_THRESHOLD or int(ip_failures or 0) >= LOCKOUT_IP_THRESHOLD


async def record_attempt(username: str, request: Request, succeeded: bool, db: AsyncSession) -> None:
    await db.execute(text("INSERT INTO auth_attempts(username,ip_hash,succeeded) VALUES(:username,:ip,:succeeded)"), {"username": username[:128], "ip": _ip_hash(request), "succeeded": succeeded})
    await db.execute(text("DELETE FROM auth_attempts WHERE created_at < NOW() - INTERVAL '30 days'"))


def has_permission(principal: Principal, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(principal.role, set())


def require_permission(permission: str):
    async def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not has_permission(principal, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Permission required: {permission}")
        return principal
    return dependency


def require_role(minimum: str):
    async def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if ROLE_ORDER.get(principal.role, 0) < ROLE_ORDER[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal
    return dependency
