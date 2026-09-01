"""JWT/RBAC boundary; disabled only for explicit local compatibility mode."""
import os, uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import bcrypt, jwt
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
TOKEN_HOURS = int(os.getenv("JWT_TOKEN_HOURS", "8"))
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
COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax").lower()
COOKIE_MAX_AGE = max(300, TOKEN_HOURS * 3600)

@dataclass(frozen=True)
class Principal:
    user_id: str | None
    username: str
    role: str
    jti: str | None = None


def hash_password(value: str) -> str:
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()


def verify_password(value: str, stored: str) -> bool:
    return bcrypt.checkpw(value.encode(), stored.encode())


def issue_token(user_id: str, username: str, role: str) -> tuple[str, str, datetime]:
    if not SECRET_KEY or SECRET_KEY == "sentinel-change-in-production":
        raise HTTPException(503, "JWT signing secret is not configured")
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    jti = str(uuid.uuid4())
    token = jwt.encode({"sub": user_id, "username": username, "role": role, "jti": jti, "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)
    return token, jti, expires


async def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> Principal:
    if not AUTH_REQUIRED:
        return Principal(None, "local-development", "SUPERADMIN")
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif session_token:
        token = session_token
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")
    return await principal_from_token(token, db)


async def require_authenticated(principal: Principal = Depends(current_principal)) -> Principal:
    return principal


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
