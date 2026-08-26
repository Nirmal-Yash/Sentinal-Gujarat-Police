"""Small JWT/RBAC boundary; disabled only for explicit local compatibility mode."""
import os, uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import bcrypt, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
TOKEN_HOURS = int(os.getenv("JWT_TOKEN_HOURS", "8"))
security = HTTPBearer(auto_error=False)
ROLE_ORDER = {"VIEWER": 1, "OPERATOR": 2, "ADMIN": 3, "SUPERADMIN": 4}

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
) -> Principal:
    if not AUTH_REQUIRED:
        return Principal(None, "local-development", "SUPERADMIN")
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")
    return await principal_from_token(credentials.credentials, db)

async def principal_from_token(token: str, db: AsyncSession) -> Principal:
    """Validate a live JWT session for both HTTP and WebSocket transports."""
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id, jti, role = claims["sub"], claims["jti"], claims["role"]
    except (jwt.PyJWTError, KeyError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    row = (await db.execute(text("""SELECT u.username, u.role FROM users u JOIN user_sessions s ON s.user_id=u.id
        WHERE u.id=CAST(:uid AS uuid) AND s.jti=CAST(:jti AS uuid) AND u.is_active=TRUE
          AND s.revoked=FALSE AND s.expires_at > NOW()"""), {"uid": user_id, "jti": jti})).mappings().first()
    if not row or row["role"] != role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is no longer valid")
    return Principal(user_id, row["username"], row["role"], jti)

async def require_authenticated(principal: Principal = Depends(current_principal)) -> Principal:
    return principal

def require_role(minimum: str):
    async def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if ROLE_ORDER.get(principal.role, 0) < ROLE_ORDER[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal
    return dependency
