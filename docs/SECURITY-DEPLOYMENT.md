# Sentinel AI — Production Security Deployment

## Required production secrets

Set these outside source control:

- `SECRET_KEY`: long random access-token signing secret.
- `JWT_REFRESH_SECRET_KEY`: different long random refresh-token signing secret.
- `SNAPSHOT_TOKEN_SECRET`: long random signed-media secret.
- `FIELD_ENCRYPTION_KEY`: Fernet key for encrypted evidence/sensitive fields.
- `POSTGRES_PASSWORD`: strong database credential.
- `REDIS_PASSWORD`: strong Redis credential when Redis authentication is enabled.
- `CCTV_PASSWORD`: assigned CCTV provider password.

Never commit `.env`, secret files, private keys, or live credentials.

## Data in transit

Production browser traffic must terminate TLS before the dashboard/API is exposed. Set `AUTH_COOKIE_SECURE=true` and `FORCE_SECURITY_HEADERS=true` behind HTTPS so session cookies are Secure and HSTS is emitted.

Set `DB_SSL=1` when PostgreSQL is reached over a TLS-capable connection. The application connection pool uses pre-ping, bounded overflow, connection recycling, statement timeout, and lock timeout.

For Redis deployments that provide TLS, use a `rediss://` Redis URL and enable Redis authentication. Local Docker development may keep the existing internal non-TLS Redis URL.

The CCTV provider remains HTTPS (`cctv.corp8.cloud`); the browser never receives `CCTV_PASSWORD`.

## Data at rest

Evidence capture computes SHA-256 over the original evidence bytes. When `FIELD_ENCRYPTION_KEY` is configured, evidence is stored encrypted on disk with a `.enc` suffix and decrypted only by the authenticated signed-evidence endpoint.

PostgreSQL, Redis, and Docker volumes should additionally be protected by encrypted host/storage volumes in the production environment. Application-level encryption is not a substitute for encrypted infrastructure storage.

Face embeddings remain queryable in PostgreSQL/pgvector because replacing the vector with ciphertext would disable the existing similarity-search feature. Protect the database volume and access controls instead.

## Authentication

Access tokens are short-lived (15 minutes by default). Refresh tokens are stored in an HttpOnly cookie, rotated on every refresh, and revoked by JTI. The application also limits concurrent sessions and applies user/IP login-failure lockout.

## Acceptance checks

1. `docker compose config -q`
2. `GET /health` returns `200`
3. `GET /ready` returns `200` with all checks true
4. Browser login sets `sentinel_session` and `sentinel_refresh` HttpOnly cookies
5. Expiring access token transparently refreshes once and retries the original request
6. `security_audit_events` receives successful/failed security-relevant request events
7. Evidence on disk is ciphertext when `FIELD_ENCRYPTION_KEY` is enabled
8. Signed evidence returns the original bytes and the stored SHA-256 header
9. Production rejects missing field-encryption/DB-TLS/secure-cookie configuration
10. Existing three CI release checks remain the only release checks

# Sentinel AI — Complete Security Hardening Plan

---

## Security Model: What This System Protects

Before any code, establish the threat model precisely. This system holds:

| Data Class | Examples | Compromise Impact |
|---|---|---|
| **BIOMETRIC** | Face embeddings, face crops | Irreversible — biometrics cannot be changed |
| **RESTRICTED** | Watchlist entries, investigation targets | Operational security failure, endangers officers |
| **SENSITIVE** | ANPR sightings, vehicle journeys, alerts | Privacy violation, investigation compromise |
| **CONFIDENTIAL** | Audit logs, user actions | Evidence tampering, accountability failure |
| **OPERATIONAL** | CCTV credentials, JWT secrets | Full system access |
| **INTERNAL** | Camera registry, vendor data | Operational disruption |

**Primary threat actors:**
1. External attacker (web-facing API, dashboard)
2. Malicious insider (low-privileged user escalating)
3. Compromised service credential (Redis, PostgreSQL)
4. Supply-chain attack (dependencies, container images)

**Core constraint:** Every security control must preserve existing business logic. No feature is disabled. No route is removed. Security wraps around the application, not through it.

---

## Layer 1: Authentication and Session Security

### 1.1 — JWT Hardening

Current state: JWT tokens issued. Expiry unknown. No rotation. No fingerprinting.

**Implement short-lived access tokens with rotating refresh tokens:**

```python
# api/core/tokens.py
import os, hashlib, secrets
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, Request

ACCESS_TOKEN_EXPIRE_MINUTES  = 15          # short window
REFRESH_TOKEN_EXPIRE_HOURS   = 8           # operator shift length
ALGORITHM                    = "HS256"
SECRET_KEY                   = os.environ["JWT_SECRET_KEY"]         # min 64 bytes
REFRESH_SECRET               = os.environ["JWT_REFRESH_SECRET_KEY"] # different key

def create_access_token(user_id: str, role: str, session_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub":        user_id,
        "role":       role,
        "sid":        session_id,           # session fingerprint
        "iat":        now,
        "exp":        now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "type":       "access",
    }, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: str, session_id: str) -> tuple[str, str]:
    """Returns (token, jti). jti is stored in DB for revocation."""
    jti = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    token = jwt.encode({
        "sub":  user_id,
        "sid":  session_id,
        "jti":  jti,
        "iat":  now,
        "exp":  now + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS),
        "type": "refresh",
    }, REFRESH_SECRET, algorithm=ALGORITHM)
    return token, jti

def fingerprint_request(request: Request) -> str:
    """Bind token to client characteristics to detect theft."""
    ua     = request.headers.get("user-agent", "")[:200]
    accept = request.headers.get("accept-language", "")[:50]
    raw    = f"{ua}|{accept}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

**Token rotation on every refresh:**

```python
# api/routes/auth.py
@router.post("/auth/refresh")
async def refresh_token(
    request: Request,
    refresh_token: str = Cookie(None),   # httpOnly cookie, not body
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(refresh_token, REFRESH_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Wrong token type")

    jti = payload["jti"]

    # Check revocation list
    revoked = await db.scalar(
        select(RevokedToken).where(RevokedToken.jti == jti)
    )
    if revoked:
        # Possible token theft — revoke entire session
        await revoke_session(payload["sid"], db)
        raise HTTPException(status_code=401, detail="Token reuse detected")

    # Rotate: revoke old refresh token, issue new pair
    await db.execute(
        insert(RevokedToken).values(jti=jti, expires_at=datetime.fromtimestamp(payload["exp"]))
    )
    user = await get_user(payload["sub"], db)
    new_access, new_refresh, new_jti = issue_token_pair(user)

    await store_refresh_jti(new_jti, user.id, db)
    await db.commit()

    response = JSONResponse({"access_token": new_access, "token_type": "bearer"})
    response.set_cookie(
        "refresh_token", new_refresh,
        httponly=True, secure=True, samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_HOURS * 3600,
        path="/api/auth/refresh",   # scope cookie to refresh endpoint only
    )
    return response
```

**Revoked tokens table migration:**

```sql
CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti        TEXT PRIMARY KEY,
    revoked_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL  -- for cleanup job
);
CREATE INDEX ON revoked_tokens(expires_at);
-- Cleanup job: DELETE FROM revoked_tokens WHERE expires_at < NOW()
```

### 1.2 — Concurrent Session Limits

```python
# Prevent credential sharing — max 3 active sessions per user
MAX_SESSIONS_PER_USER = 3

async def enforce_session_limit(user_id: str, db: AsyncSession):
    sessions = await db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user_id, UserSession.expires_at > datetime.now(timezone.utc))
        .order_by(UserSession.created_at.asc())
    )
    session_list = list(sessions)
    if len(session_list) >= MAX_SESSIONS_PER_USER:
        # Evict oldest session
        oldest = session_list[0]
        await db.execute(
            insert(RevokedToken).values(jti=oldest.jti, expires_at=oldest.expires_at)
        )
        await db.delete(oldest)
        # Log security event
        await audit_security_event("SESSION_EVICTED",
            f"Session evicted for {user_id}: max concurrent sessions reached")
```

### 1.3 — Password Policy Enforcement

**Backend enforcement (not just frontend):**

```python
# api/core/password_policy.py
import re

class PasswordPolicyViolation(ValueError):
    pass

COMMON_PASSWORDS = {
    "password123", "sentinel123", "admin123", "gujarat2024",
    "police123", "123456789", "qwerty123", "letmein123"
}

def enforce_password_policy(password: str, username: str) -> None:
    errors = []

    if len(password) < 12:
        errors.append("Minimum 12 characters required")
    if len(password) > 128:
        errors.append("Maximum 128 characters allowed")
    if not re.search(r"[A-Z]", password):
        errors.append("At least one uppercase letter required")
    if not re.search(r"[a-z]", password):
        errors.append("At least one lowercase letter required")
    if not re.search(r"\d", password):
        errors.append("At least one digit required")
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{}|;:,.<>?]", password):
        errors.append("At least one special character required")
    if username.lower() in password.lower():
        errors.append("Password must not contain your username")
    if password.lower() in COMMON_PASSWORDS:
        errors.append("Password is too common")
    if len(set(password)) < 6:
        errors.append("Password is too repetitive")

    if errors:
        raise PasswordPolicyViolation("; ".join(errors))
```

### 1.4 — Account Lockout Hardening

Extend the existing `auth_attempts` system with IP-level and user-level lockout:

```python
# api/core/lockout.py
LOCKOUT_CONFIG = {
    "per_user": {
        "threshold": 5,
        "window_minutes": 15,
        "lockout_minutes": 30,
    },
    "per_ip": {
        "threshold": 20,        # higher — shared office NAT
        "window_minutes": 15,
        "lockout_minutes": 60,
    },
    "progressive": {
        # After 3 lockouts, extend to 24 hours
        "repeated_lockouts": 3,
        "extended_lockout_hours": 24,
    }
}

async def check_lockout(username: str, ip: str, db) -> tuple[bool, str]:
    """Returns (is_locked, reason)."""

    # User lockout
    user_failures = await count_recent_failures(username=username, window_minutes=15, db=db)
    if user_failures >= LOCKOUT_CONFIG["per_user"]["threshold"]:
        return True, f"Account locked: {LOCKOUT_CONFIG['per_user']['lockout_minutes']} minutes"

    # IP lockout
    ip_failures = await count_recent_failures(ip=ip, window_minutes=15, db=db)
    if ip_failures >= LOCKOUT_CONFIG["per_ip"]["threshold"]:
        return True, f"IP locked: too many failed attempts from this network"

    return False, ""
```

---

## Layer 2: API Security

### 2.1 — Rate Limiting: Complete Endpoint Inventory

Different endpoints have different risk profiles. Apply per-endpoint limits:

```python
# api/middleware/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri=os.environ["REDIS_URL"])

RATE_LIMITS = {
    # Authentication — hardest limits
    "auth_login":          "5/minute",
    "auth_refresh":        "30/minute",
    "auth_password_change":"3/hour",

    # Investigation — expensive operations
    "investigate_plate":   "30/minute",
    "investigate_person":  "10/minute",   # embedding extraction is heavy

    # Watchlist — sensitive data
    "watchlist_read":      "100/minute",
    "watchlist_write":     "10/minute",

    # Evidence — large file serving
    "evidence_serve":      "200/minute",
    "snapshot":            "120/minute",  # 30 cameras × 4/sec max

    # Alert actions — should be deliberate
    "alert_action":        "60/minute",

    # Registry writes
    "camera_import":       "5/hour",
    "camera_create":       "30/minute",

    # General API
    "api_general":         "500/minute",
}
```

Apply in routes:

```python
@router.post("/auth/login")
@limiter.limit(RATE_LIMITS["auth_login"])
async def login(request: Request, ...):
    ...

@router.post("/investigate/person")
@limiter.limit(RATE_LIMITS["investigate_person"])
async def investigate_person(request: Request, ...):
    ...
```

### 2.2 — CORS: Lock to Known Origins

```python
# api/main.py
from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,       # explicit list, NEVER "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Test-Session-Id", "X-CSRF-Token"],
    expose_headers=["X-Request-Id"],
    max_age=600,
)
```

Environment variable in `docker-compose.yml`:
```yaml
api:
  environment:
    ALLOWED_ORIGINS: "https://your-dashboard-domain.com,http://localhost:3000"
```

### 2.3 — Request Size Limits by Endpoint

```python
# api/middleware/size_limits.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

SIZE_LIMITS = {
    "/api/investigate/person":    10 * 1024 * 1024,  # 10 MB — face photo
    "/api/test-sessions/videos":  200 * 1024 * 1024, # 200 MB — test video
    "/api/camera-imports":        5 * 1024 * 1024,   # 5 MB — CSV/XLSX
    "/api/watchlist":             2 * 1024 * 1024,   # 2 MB — watchlist photo
    "default":                    1 * 1024 * 1024,   # 1 MB — all other requests
}

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            path = request.url.path
            limit = next(
                (v for k, v in SIZE_LIMITS.items() if path.startswith(k)),
                SIZE_LIMITS["default"]
            )
            if int(content_length) > limit:
                raise HTTPException(
                    status_code=413,
                    detail=f"Request too large. Maximum: {limit // 1024 // 1024} MB"
                )
        return await call_next(request)
```

### 2.4 — SSRF Prevention for Camera URLs

The camera proxy, GNS3-style imports, and any user-supplied URL must be validated against an allowlist:

```python
# api/core/ssrf_protection.py
import ipaddress
from urllib.parse import urlparse

ALLOWED_EXTERNAL_HOSTS = {
    "cctv.corp8.cloud",
    "stream.corp8.cloud",
    "103.250.160.189",   # direct IP for RTSP
}

BLOCKED_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("100.64.0.0/10"),   # Tailscale/CG-NAT
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

def validate_external_url(url: str, allow_schemes: set[str] = {"https"}) -> str:
    """
    Validate that a URL is safe to proxy to.
    Raises ValueError with a safe (non-leaking) error message on rejection.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL format")

    if parsed.scheme not in allow_schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not permitted")

    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")

    if host not in ALLOWED_EXTERNAL_HOSTS:
        # Attempt DNS resolution to check for SSRF via DNS rebinding
        import socket
        try:
            resolved_ip = socket.gethostbyname(host)
            ip = ipaddress.ip_address(resolved_ip)
            for blocked in BLOCKED_IP_RANGES:
                if ip in blocked:
                    raise ValueError("URL resolves to a private address")
        except socket.gaierror:
            raise ValueError("Hostname could not be resolved")
        raise ValueError("URL host is not on the permitted list")

    return url


def validate_rtsp_url(url: str) -> str:
    """RTSP-specific validation — also allows rtsp:// scheme."""
    return validate_external_url(url, allow_schemes={"rtsp", "rtsps"})

def validate_hls_url(url: str) -> str:
    return validate_external_url(url, allow_schemes={"https"})
```

Apply in every endpoint that accepts a URL:

```python
# Camera creation
@router.post("/cameras")
async def create_camera(data: CameraCreate, ...):
    if data.rtsp_url:
        try:
            data.rtsp_url = validate_rtsp_url(data.rtsp_url)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid RTSP URL: {e}")
    if data.hls_url:
        try:
            data.hls_url = validate_hls_url(data.hls_url)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid HLS URL: {e}")
```

---

## Layer 3: Input Validation — Complete Field Inventory

Every input field in the system. This is the complete map.

### 3.1 — Validation Schema Library

```python
# api/core/validators.py
import re
from pydantic import validator, field_validator
from typing import Annotated
from pydantic import StringConstraints

# ── Plate numbers ─────────────────────────────────────────────────────────────
INDIAN_PLATE_RE = re.compile(
    r'^[A-Z]{2}\d{2}[A-Z]{1,3}\d{4}$'          # standard: GJ01AB1234
    r'|^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$'            # two-letter series
    r'|^[A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4}$'        # partial plates
)
def validate_plate_number(plate: str) -> str:
    if not plate or not plate.strip():
        raise ValueError("Plate number is required")
    normalised = re.sub(r'[\s\-_\.]', '', plate.upper().strip())
    if len(normalised) < 4 or len(normalised) > 12:
        raise ValueError("Plate number length invalid (4-12 alphanumeric characters)")
    if not re.match(r'^[A-Z0-9]+$', normalised):
        raise ValueError("Plate number contains invalid characters")
    return normalised

# ── Names and labels ──────────────────────────────────────────────────────────
SafeName = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=100,
    pattern=r'^[A-Za-z0-9\s\-_.,\'()&]+$'
)]

# ── Free text (notes, reasons) ────────────────────────────────────────────────
SafeText = Annotated[str, StringConstraints(
    strip_whitespace=True,
    max_length=2000,
)]
def sanitise_freetext(text: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    import html
    text = html.escape(text)            # encode < > & " '
    text = re.sub(r'\s+', ' ', text)   # normalise whitespace
    return text.strip()

# ── Coordinates ───────────────────────────────────────────────────────────────
def validate_lat(v: float) -> float:
    if not (-90 <= v <= 90):
        raise ValueError(f"Latitude must be between -90 and 90, got {v}")
    return round(v, 8)

def validate_lng(v: float) -> float:
    if not (-180 <= v <= 180):
        raise ValueError(f"Longitude must be between -180 and 180, got {v}")
    return round(v, 8)

# ── Usernames ─────────────────────────────────────────────────────────────────
USERNAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.\-]{2,31}$')
def validate_username(v: str) -> str:
    v = v.strip()
    if not USERNAME_RE.fullmatch(v):
        raise ValueError("Username must be 3-32 characters: letters, digits, _, ., or -")
    if v.lower() in {"admin", "root", "system", "administrator", "superadmin", "api", "null"}:
        raise ValueError("That username is reserved")
    return v

# ── UUIDs ─────────────────────────────────────────────────────────────────────
UUID4_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
)
def validate_uuid(v: str) -> str:
    if not UUID4_RE.fullmatch(v.lower()):
        raise ValueError("Invalid ID format")
    return v.lower()

# ── Search queries ────────────────────────────────────────────────────────────
def validate_search_query(v: str, max_len: int = 100) -> str:
    v = v.strip()
    if len(v) > max_len:
        raise ValueError(f"Search query too long (max {max_len} characters)")
    # Strip SQL wildcards and injection patterns
    v = re.sub(r"[;'\"\-\-\/\*\\]", "", v)
    return v
```

### 3.2 — Field Validation by Feature

**Authentication forms:**

```python
class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    def clean_username(cls, v):
        v = v.strip()[:128]
        if not v:
            raise ValueError("Username is required")
        # Don't reveal which validation failed — generic error to prevent enumeration
        return v

    @field_validator("password")
    def clean_password(cls, v):
        if not v or len(v) < 1:
            raise ValueError("Password is required")
        if len(v) > 256:
            raise ValueError("Invalid credentials")  # don't reveal max length
        return v
```

**Watchlist entry:**

```python
class WatchlistCreate(BaseModel):
    name:        str
    plate_number: str | None = None
    reason:      str
    priority:    Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    notes:       str | None = None

    @field_validator("name")
    def clean_name(cls, v):
        v = v.strip()
        if not v or len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Name must not exceed 100 characters")
        if not re.match(r"^[A-Za-z0-9\s\-'.,()]+$", v):
            raise ValueError("Name contains invalid characters")
        return v

    @field_validator("plate_number", mode="before")
    def clean_plate(cls, v):
        if v is None:
            return None
        return validate_plate_number(v)

    @field_validator("reason")
    def clean_reason(cls, v):
        return sanitise_freetext(v)[:500]

    @field_validator("notes")
    def clean_notes(cls, v):
        if v is None:
            return None
        return sanitise_freetext(v)[:2000]
```

**Camera registration:**

```python
class CameraCreate(BaseModel):
    name:         str
    external_id:  str | None = None
    rtsp_url:     str | None = None
    hls_url:      str | None = None
    lat:          float | None = None
    lng:          float | None = None
    location:     str | None = None
    vendor_id:    str | None = None
    model_id:     str | None = None
    notes:        str | None = None

    @field_validator("name")
    def clean_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Camera name is required")
        if len(v) > 100:
            raise ValueError("Camera name too long (max 100 characters)")
        if re.search(r'[<>"\';\\]', v):
            raise ValueError("Camera name contains invalid characters")
        return v

    @field_validator("external_id")
    def clean_external_id(cls, v):
        if v is None:
            return None
        v = v.strip()
        if not re.match(r'^[A-Za-z0-9_\-]{1,50}$', v):
            raise ValueError("Camera ID must be alphanumeric (1-50 characters)")
        return v

    @field_validator("rtsp_url")
    def clean_rtsp_url(cls, v):
        if v is None:
            return None
        try:
            return validate_rtsp_url(v.strip())
        except ValueError as e:
            raise ValueError(str(e))

    @field_validator("hls_url")
    def clean_hls_url(cls, v):
        if v is None:
            return None
        try:
            return validate_hls_url(v.strip())
        except ValueError as e:
            raise ValueError(str(e))

    @field_validator("lat")
    def clean_lat(cls, v):
        if v is None:
            return None
        return validate_lat(v)

    @field_validator("lng")
    def clean_lng(cls, v):
        if v is None:
            return None
        return validate_lng(v)

    @field_validator("location")
    def clean_location(cls, v):
        if v is None:
            return None
        return sanitise_freetext(v.strip())[:200]

    @field_validator("vendor_id", "model_id")
    def clean_uuid(cls, v):
        if v is None:
            return None
        return validate_uuid(v)
```

**Investigation requests:**

```python
class PlateInvestigationRequest(BaseModel):
    plate:     str
    date_from: datetime | None = None
    date_to:   datetime | None = None

    @field_validator("plate")
    def clean_plate(cls, v):
        return validate_plate_number(v)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to:
            if self.date_from > self.date_to:
                raise ValueError("date_from must be before date_to")
            max_range = timedelta(days=365)
            if (self.date_to - self.date_from) > max_range:
                raise ValueError("Date range cannot exceed 1 year")
        if self.date_to and self.date_to > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("date_to cannot be in the future")
        return self
```

**Alert filters:**

```python
class AlertFilterParams(BaseModel):
    status:     Literal["NEW","ACKNOWLEDGED","INVESTIGATING","RESOLVED","CLOSED"] | None = None
    alert_type: Literal["WATCHLIST_HIT","PLATE_SIGHTING","CROWD_ANOMALY","RUNNING_CROWD","SYSTEM"] | None = None
    plate_text: str | None = None
    camera_id:  str | None = None
    date_from:  datetime | None = None
    date_to:    datetime | None = None
    limit:      int = 100
    offset:     int = 0

    @field_validator("plate_text")
    def clean_plate(cls, v):
        if v is None:
            return None
        return validate_plate_number(v)

    @field_validator("camera_id")
    def clean_camera_id(cls, v):
        if v is None:
            return None
        return validate_uuid(v)

    @field_validator("limit")
    def clean_limit(cls, v):
        return max(1, min(500, v))

    @field_validator("offset")
    def clean_offset(cls, v):
        return max(0, min(10000, v))
```

### 3.3 — Frontend Input Validation (Mirror of Backend)

Every input field must validate before the API call:

```javascript
// utils/validators.js

export const validators = {
  plateNumber: (value) => {
    const normalised = value.replace(/[\s\-_.]/g, '').toUpperCase();
    if (!normalised) return 'Plate number is required';
    if (normalised.length < 4 || normalised.length > 12)
      return 'Plate number must be 4-12 characters';
    if (!/^[A-Z0-9]+$/.test(normalised))
      return 'Plate number can only contain letters and numbers';
    return null; // valid
  },

  cameraName: (value) => {
    const v = value?.trim();
    if (!v) return 'Camera name is required';
    if (v.length > 100) return 'Name too long (max 100 characters)';
    if (/[<>"';\\]/.test(v)) return 'Name contains invalid characters';
    return null;
  },

  coordinates: {
    lat: (value) => {
      const n = parseFloat(value);
      if (isNaN(n)) return 'Latitude must be a number';
      if (n < -90 || n > 90) return 'Latitude must be between -90 and 90';
      return null;
    },
    lng: (value) => {
      const n = parseFloat(value);
      if (isNaN(n)) return 'Longitude must be a number';
      if (n < -180 || n > 180) return 'Longitude must be between -180 and 180';
      return null;
    },
  },

  rtspUrl: (value) => {
    if (!value) return null; // optional
    if (!value.startsWith('rtsp://') && !value.startsWith('rtsps://'))
      return 'RTSP URL must start with rtsp:// or rtsps://';
    try { new URL(value.replace('rtsp://', 'http://').replace('rtsps://', 'https://')); }
    catch { return 'Invalid RTSP URL format'; }
    return null;
  },

  hlsUrl: (value) => {
    if (!value) return null;
    if (!value.startsWith('https://'))
      return 'HLS URL must use HTTPS';
    try { new URL(value); }
    catch { return 'Invalid HLS URL format'; }
    return null;
  },

  freeText: (value, maxLen = 2000) => {
    if (value && value.length > maxLen)
      return `Text too long (max ${maxLen} characters)`;
    return null;
  },

  dateRange: (from, to) => {
    if (from && to) {
      if (new Date(from) > new Date(to))
        return 'Start date must be before end date';
      const daysDiff = (new Date(to) - new Date(from)) / (86400 * 1000);
      if (daysDiff > 365)
        return 'Date range cannot exceed one year';
    }
    return null;
  },
};

// Hook for field-level validation
export function useFieldValidation(validator) {
  const [error, setError] = useState(null);
  const [touched, setTouched] = useState(false);

  const validate = useCallback((value) => {
    const result = validator(value);
    setError(result);
    return result === null;
  }, [validator]);

  const onBlur = useCallback((value) => {
    setTouched(true);
    validate(value);
  }, [validate]);

  return {
    error: touched ? error : null,
    validate,
    onBlur,
    setTouched,
  };
}
```

**Form field component with validation:**

```javascript
// components/ValidatedInput.jsx
export function ValidatedInput({
  label,
  value,
  onChange,
  validator,
  type = "text",
  required = false,
  placeholder,
  helpText,
  ...props
}) {
  const { error, onBlur } = useFieldValidation(validator || (() => null));

  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-zinc-300">
        {label}
        {required && <span className="text-red-400 ml-1">*</span>}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={(e) => onBlur(e.target.value)}
        placeholder={placeholder}
        aria-invalid={!!error}
        aria-describedby={error ? `${label}-error` : undefined}
        className={cn(
          "w-full px-3 py-2 rounded-md text-sm bg-zinc-900 border",
          "transition-colors duration-150 outline-none",
          "focus:ring-2 focus:ring-amber-500/40",
          error
            ? "border-red-500 focus:border-red-400"
            : "border-zinc-700 focus:border-amber-500"
        )}
        {...props}
      />
      {error && (
        <p id={`${label}-error`} className="text-xs text-red-400 flex items-center gap-1">
          <AlertCircle className="h-3 w-3" />
          {error}
        </p>
      )}
      {!error && helpText && (
        <p className="text-xs text-zinc-500">{helpText}</p>
      )}
    </div>
  );
}
```

---

## Layer 4: File Upload Security

### 4.1 — Complete File Validation Pipeline

Every file upload goes through the same pipeline regardless of endpoint:

```python
# api/core/file_security.py
import magic          # python-magic — reads actual file bytes, not extension
import hashlib
from PIL import Image
import io

ALLOWED_MIME_TYPES = {
    "investigation_photo": {
        "image/jpeg", "image/png", "image/webp",
        # NOT image/heic, image/heif — require conversion before upload
    },
    "watchlist_photo": {
        "image/jpeg", "image/png", "image/webp",
    },
    "test_video": {
        "video/mp4", "video/quicktime",
    },
    "camera_import": {
        "text/csv", "text/plain",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
}

EXTENSION_TO_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".webp": "image/webp",
    ".mp4": "video/mp4",  ".mov": "video/quicktime",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

def validate_upload(
    content: bytes,
    filename: str,
    upload_type: str,
    max_size_bytes: int,
) -> dict:
    """
    Full upload validation pipeline:
    1. Size check
    2. MIME type from magic bytes (not extension)
    3. Extension consistency check
    4. Image integrity check (for images)
    5. SHA-256 computation
    Returns validated metadata or raises HTTPException.
    """
    # 1. Size
    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(content)//1024//1024} MB. "
                   f"Maximum: {max_size_bytes//1024//1024} MB"
        )

    if len(content) < 16:
        raise HTTPException(status_code=400, detail="File is too small to be valid")

    # 2. Real MIME type from magic bytes
    real_mime = magic.from_buffer(content[:8192], mime=True)
    allowed = ALLOWED_MIME_TYPES.get(upload_type, set())
    if real_mime not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"File type '{real_mime}' is not allowed for this upload"
        )

    # 3. Extension consistency
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    expected_mime = EXTENSION_TO_MIME.get(ext)
    if expected_mime and expected_mime != real_mime:
        raise HTTPException(
            status_code=415,
            detail="File extension does not match file content"
        )

    # 4. Image integrity (cannot be corrupted or contain embedded payload)
    if real_mime.startswith("image/"):
        try:
            img = Image.open(io.BytesIO(content))
            img.verify()   # raises if corrupted
            # Re-open after verify (verify invalidates the object)
            img = Image.open(io.BytesIO(content))
            width, height = img.size
            if width < 10 or height < 10:
                raise ValueError("Image too small")
            if width > 8000 or height > 8000:
                raise ValueError("Image dimensions too large")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid image file: {e}")

    # 5. SHA-256 for evidence chain
    digest = hashlib.sha256(content).hexdigest()

    return {
        "mime_type": real_mime,
        "size_bytes": len(content),
        "sha256": digest,
        "filename_safe": sanitise_filename(filename),
    }


def sanitise_filename(filename: str) -> str:
    """Remove path components and dangerous characters from filenames."""
    import pathlib
    # Take only the base name — strip any directory traversal
    name = pathlib.Path(filename).name
    # Replace all non-alphanumeric except . - _
    name = re.sub(r'[^A-Za-z0-9.\-_]', '_', name)
    # Prevent hidden files
    name = name.lstrip('.')
    # Limit length
    stem, _, suffix = name.rpartition('.')
    return f"{stem[:80]}.{suffix[:10]}" if suffix else name[:80]
```

### 4.2 — Stored File Path Security

```python
# api/core/storage.py
import uuid
from pathlib import Path

STORAGE_ROOT = Path(os.environ["EVIDENCE_STORAGE_PATH"])

def generate_storage_path(category: str, extension: str) -> tuple[str, Path]:
    """
    Generate a collision-resistant, path-traversal-safe storage path.
    Returns (relative_key, absolute_path).
    Category is validated against allowlist.
    """
    allowed_categories = {"alerts", "faces", "anpr_crops", "evidence", "watchlist"}
    if category not in allowed_categories:
        raise ValueError(f"Invalid storage category: {category}")

    file_id   = str(uuid.uuid4())
    now       = datetime.now(timezone.utc)
    # Hierarchical path for filesystem performance at scale
    rel_path  = f"{category}/{now.year}/{now.month:02d}/{now.day:02d}/{file_id}.{extension}"
    abs_path  = STORAGE_ROOT / rel_path

    # Verify the resolved path is within STORAGE_ROOT (path traversal guard)
    if STORAGE_ROOT.resolve() not in abs_path.resolve().parents:
        raise ValueError("Storage path escapes storage root")

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return rel_path, abs_path
```

---

## Layer 5: Database Security

### 5.1 — Query Safety: No String Interpolation Anywhere

Enforce at the codebase level — search for and eliminate any raw SQL string formatting:

```bash
# Audit: find potentially unsafe SQL patterns
grep -rn "f\"SELECT\|f'SELECT\|% SELECT\|format.*SELECT\|+ \" SELECT" api/ --include="*.py"
grep -rn "f\"INSERT\|f\"UPDATE\|f\"DELETE" api/ --include="*.py"
```

All queries must use bound parameters:

```python
# NEVER this:
await db.execute(f"SELECT * FROM cameras WHERE name = '{name}'")

# ALWAYS this:
await db.execute(
    select(Camera).where(Camera.name == name)  # ORM
)
# OR:
await db.execute(
    text("SELECT * FROM cameras WHERE name = :name"),
    {"name": name}
)
```

### 5.2 — Database User Privilege Separation

```sql
-- Production: application user has NO DDL rights
CREATE USER sentinel_app WITH PASSWORD '<strong-password>';
GRANT CONNECT ON DATABASE sentinel TO sentinel_app;
GRANT USAGE ON SCHEMA public TO sentinel_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sentinel_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO sentinel_app;

-- Migration user: runs migrations only, separate credential
CREATE USER sentinel_migration WITH PASSWORD '<different-strong-password>';
GRANT ALL ON DATABASE sentinel TO sentinel_migration;

-- Read-only user: for audit exports, reports
CREATE USER sentinel_readonly WITH PASSWORD '<readonly-password>';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sentinel_readonly;
```

Use in environment:
```env
DATABASE_URL=postgresql://sentinel_app:password@postgres:5432/sentinel
DATABASE_MIGRATION_URL=postgresql://sentinel_migration:password@postgres:5432/sentinel
```

### 5.3 — Sensitive Field Encryption at Rest

Face embeddings and watchlist reason fields contain biometric and sensitive operational data. Encrypt before storing:

```python
# api/core/encryption.py
from cryptography.fernet import Fernet
import base64, os

class FieldEncryption:
    def __init__(self):
        key = os.environ["FIELD_ENCRYPTION_KEY"].encode()
        # Key must be 32 bytes, base64url-encoded (Fernet requirement)
        self._fernet = Fernet(key)

    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._fernet.decrypt(data)

    def encrypt_text(self, text: str) -> str:
        return base64.b64encode(self.encrypt(text.encode())).decode()

    def decrypt_text(self, ciphertext: str) -> str:
        return self.decrypt(base64.b64decode(ciphertext)).decode()

field_encryption = FieldEncryption()
```

Apply to watchlist reason/notes and face embeddings:

```python
# Before storing a watchlist entry
entry.reason_encrypted = field_encryption.encrypt_text(plain_reason)
entry.reason = "[ENCRYPTED]"   # never store plain in main column

# Before storing a face embedding
embedding_bytes = embedding_array.astype(np.float32).tobytes()
entry.embedding_encrypted = field_encryption.encrypt(embedding_bytes)
entry.embedding = None   # never store plain
```

### 5.4 — Connection Pool Hardening

```python
# api/database.py
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    os.environ["DATABASE_URL"],
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,       # recycle connections every 30 min
    pool_pre_ping=True,      # verify connection before using
    echo=False,              # NEVER True in production — leaks SQL to logs
    connect_args={
        "server_settings": {
            "application_name": "sentinel_api",
            "statement_timeout": "30000",    # 30s query timeout
            "lock_timeout": "10000",          # 10s lock timeout
        },
        "ssl": "require" if os.getenv("DB_SSL", "1") == "1" else "prefer",
    },
)
```

---

## Layer 6: Frontend Application Security

### 6.1 — Content Security Policy

Replace the permissive existing CSP with a strict policy:

```python
# api/middleware/security_headers.py

@app.after_request   # or equivalent FastAPI middleware
def security_headers(response):
    # Generate a per-request nonce for inline scripts
    nonce = base64.b64encode(os.urandom(16)).decode()

    response.headers.update({
        # CSP — adjust src allowlists to match your actual dependencies
        "Content-Security-Policy": (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            f"style-src 'self' 'unsafe-inline'; "   # unsafe-inline only for CSS
            f"img-src 'self' data: blob:; "          # blob: for HLS video
            f"media-src 'self' blob:; "              # video elements
            f"connect-src 'self' wss: ws:; "         # WebSocket for alerts
            f"worker-src blob:; "                     # HLS.js worker
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self';"
        ),
        "X-Frame-Options":           "DENY",
        "X-Content-Type-Options":    "nosniff",
        "Referrer-Policy":           "strict-origin-when-cross-origin",
        "Permissions-Policy": (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        ),
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "X-Request-Id":              str(uuid.uuid4()),
        "Cache-Control":             "no-store",     # default; override per-route for assets
    })
    # Never reveal server/framework identity
    response.headers.pop("Server", None)
    response.headers.pop("X-Powered-By", None)
    return response
```

### 6.2 — XSS Prevention: DOMPurify on All Rendered Data

Install: `npm install dompurify`

```javascript
// utils/sanitise.js
import DOMPurify from 'dompurify';

// Use for any value rendered as HTML
export const sanitiseHtml = (dirty) =>
  DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: [],      // strip ALL tags — we want text only
    ALLOWED_ATTR: [],
  });

// Apply to: camera names, alert messages, vendor names, location strings
// Anywhere that comes from the API and goes into the DOM

// In components:
function CameraName({ name }) {
  return <span>{sanitiseHtml(name)}</span>;
}

// Alert details — most dangerous surface (could contain OCR text from plates)
function AlertDetail({ alert }) {
  return (
    <div>
      <span className="font-mono">{sanitiseHtml(alert.plate_text)}</span>
      <p>{sanitiseHtml(alert.details)}</p>
    </div>
  );
}
```

### 6.3 — CSRF: Consistent Double-Submit Cookie Pattern

Current CSRF is inconsistent across routes. Standardise:

```javascript
// api/client.js
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('sentinel_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;

  // CSRF: double-submit for state-mutating requests
  const METHOD = (config.method || 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(METHOD)) {
    const csrf = getCSRFToken();    // from session/cookie
    if (csrf) config.headers['X-CSRF-Token'] = csrf;
  }

  // Test session
  const testSession = sessionStorage.getItem('sentinel_test_session');
  if (testSession) {
    const { session_id } = JSON.parse(testSession);
    config.headers['X-Test-Session-Id'] = session_id;
  }

  return config;
});
```

Backend verification:

```python
def verify_csrf(request: Request) -> None:
    """Call this at the top of every state-mutating endpoint."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return  # safe methods don't need CSRF

    # Skip for API clients with Bearer token auth (they're not browser-form-submit vulnerable)
    # Only enforce for session-cookie-based auth
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return  # JWT auth doesn't need CSRF

    csrf_header = request.headers.get("X-CSRF-Token")
    session_csrf = request.session.get("csrf")

    if not csrf_header or not session_csrf:
        raise HTTPException(status_code=403, detail="CSRF token required")

    if not hmac.compare_digest(csrf_header, session_csrf):
        raise HTTPException(status_code=403, detail="CSRF token invalid")
```

### 6.4 — Sensitive Data: Never Log, Never Cache

```javascript
// The following must NEVER appear in:
// - console.log() statements
// - localStorage
// - URL query parameters
// - Browser history

NEVER_LOG = [
  'password', 'access_token', 'refresh_token',
  'cctv_password', 'embedding', 'face_data'
];

// Use this wrapper for development logging:
function devLog(...args) {
  if (process.env.NODE_ENV !== 'development') return;
  const safe = args.map(arg => {
    if (typeof arg !== 'object') return arg;
    const cleaned = { ...arg };
    NEVER_LOG.forEach(key => {
      if (key in cleaned) cleaned[key] = '[REDACTED]';
    });
    return cleaned;
  });
  console.log('[DEV]', ...safe);
}
```

---

## Layer 7: Container and Infrastructure Security

### 7.1 — Dockerfile Hardening (All Services)

```dockerfile
# api/Dockerfile
FROM python:3.12-slim AS base

# Run as non-root — never run as uid 0 in containers
RUN groupadd -r sentinel && useradd -r -g sentinel sentinel

# Install system deps as root, then drop
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps before copying code (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY --chown=sentinel:sentinel . .

# Drop privileges
USER sentinel

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# No shell in production — use exec form
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--no-access-log"]
```

```dockerfile
# dashboard/Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build

FROM nginx:alpine AS runtime
# Non-root nginx
RUN adduser -D -H -u 1000 -s /sbin/nologin www-user
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
USER www-user
EXPOSE 3000
```

### 7.2 — Docker Compose Security Hardening

```yaml
# docker-compose.yml additions for every service:

services:
  api:
    security_opt:
      - no-new-privileges:true      # prevent setuid escalation
    read_only: true                  # read-only filesystem
    tmpfs:
      - /tmp:size=256m,mode=1777    # writable tmp in RAM only
    cap_drop:
      - ALL                          # drop all Linux capabilities
    cap_add:
      - NET_BIND_SERVICE             # only if binding ports < 1024
    mem_limit: 512m
    memswap_limit: 512m
    cpus: "2.0"
    user: "1000:1000"               # non-root UID:GID
    networks:
      - backend                     # service-specific network
    # NEVER expose ports unless required by the service
    # expose: only for internal service communication

  postgres:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data:Z   # :Z for SELinux
    networks:
      - backend
    # No port mapping — only accessible within Docker network

  redis:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    command: redis-server --requirepass "${REDIS_PASSWORD}" --maxmemory 512mb --maxmemory-policy allkeys-lru
    networks:
      - backend

networks:
  backend:
    driver: bridge
    internal: true      # no external internet access
  frontend:
    driver: bridge       # dashboard ↔ api only

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

### 7.3 — Secrets Management

**All secrets must come from environment, never from code or config files:**

```bash
# .env.example — commit this
JWT_SECRET_KEY=                    # min 64 bytes, random: openssl rand -hex 64
JWT_REFRESH_SECRET_KEY=            # different key
FIELD_ENCRYPTION_KEY=              # Fernet key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CCTV_PASSWORD=                     # injected only into services that need it
SNAPSHOT_TOKEN_SECRET=             # min 32 bytes
REDIS_PASSWORD=                    # min 32 chars random
DATABASE_URL=                      # postgresql://user:pass@host/db
ALLOWED_ORIGINS=https://your-domain.com

# .env — NEVER commit, in .gitignore
# .gitignore must contain:
.env
.env.*
!.env.example
secrets/
*.key
*.pem
*.p12
*.pfx
```

**Secret rotation checklist** (run quarterly):

```bash
scripts/rotate_secrets.sh:
  - Generate new JWT_SECRET_KEY → forces all sessions to re-login
  - Generate new FIELD_ENCRYPTION_KEY → requires re-encryption of stored data
  - Rotate CCTV_PASSWORD → coordinate with cctv.corp8.cloud
  - Rotate REDIS_PASSWORD → update all services
  - Rotate database passwords → update DATABASE_URL in all services
  - Rotate SNAPSHOT_TOKEN_SECRET → existing snapshot URLs immediately invalid
```

---

## Layer 8: Network Security

### 8.1 — Internal Service Communication

Services communicate only through defined channels. No service should talk to another service's database directly:

```
API → PostgreSQL:   allowed (app user, read/write specific tables)
API → Redis:        allowed (app operations)
AI  → Redis:        allowed (publish detection events)
AI  → PostgreSQL:   allowed (write sightings only — not all tables)
Intelligence → Redis: allowed (subscribe + publish)
Intelligence → PostgreSQL: allowed (write alerts, read watchlist)
Dashboard → API:    allowed (all dashboard operations through API only)
Dashboard → PostgreSQL: NEVER (no direct DB access from frontend container)
Dashboard → Redis:  NEVER
AI → external:      NEVER (AI services have no internet access)
```

Enforce with Docker network segregation:

```yaml
networks:
  api_db:      # api ↔ postgres
  api_redis:   # api ↔ redis
  ai_redis:    # ai ↔ redis
  intel_redis: # intelligence ↔ redis
  frontend:    # dashboard ↔ api only
```

### 8.2 — Redis Security

```python
# All Redis operations use namespaced keys to prevent cross-contamination
REDIS_KEY_PREFIXES = {
    "production": "sentinel:prod:",
    "test":       "sentinel:test:",
    "sessions":   "sentinel:sessions:",
    "dedup":      "sentinel:dedup:",
    "ratelimit":  "sentinel:rl:",
    "watchlist":  "sentinel:wl:",
}

def make_key(category: str, *parts: str) -> str:
    prefix = REDIS_KEY_PREFIXES.get(category, f"sentinel:{category}:")
    return prefix + ":".join(str(p) for p in parts)
```

Redis must run with:
- `requirepass` — mandatory
- `protected-mode yes` — default on, keep it
- `bind 127.0.0.1` in single-host / bind to internal Docker network IP only
- `maxmemory` and `maxmemory-policy` — prevent memory exhaustion attacks

### 8.3 — CCTV Proxy: Prevent Credential Leakage

The CCTV password must never appear in:
- Request URLs (even as a query parameter)
- Response headers
- Browser network tab
- Application logs
- Error messages

```python
# api/middleware/credential_scrubber.py

SENSITIVE_PATTERNS = [
    re.compile(r'password=[^&\s]+', re.IGNORECASE),
    re.compile(r'Bearer [A-Za-z0-9._-]{20,}'),
    re.compile(os.environ.get("CCTV_PASSWORD", "PLACEHOLDER"), re.IGNORECASE),
]

def scrub_sensitive(text: str) -> str:
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text

# Apply to all log output
import logging

class ScrubFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = scrub_sensitive(record.msg)
        return True

logging.getLogger().addFilter(ScrubFilter())
```

---

## Layer 9: Audit and Security Monitoring

### 9.1 — Security Event Taxonomy

Every security-relevant event is logged with this structure:

```python
# api/core/security_audit.py

SECURITY_EVENTS = {
    # Authentication
    "AUTH_LOGIN_SUCCESS":        "LOW",
    "AUTH_LOGIN_FAILURE":        "MEDIUM",
    "AUTH_LOGIN_LOCKED":         "HIGH",
    "AUTH_TOKEN_REFRESH":        "LOW",
    "AUTH_TOKEN_REUSE_DETECTED": "CRITICAL",    # possible theft
    "AUTH_SESSION_REVOKED":      "HIGH",
    "AUTH_LOGOUT":               "LOW",
    "AUTH_PASSWORD_CHANGED":     "MEDIUM",
    "AUTH_FORCE_CHANGE":         "MEDIUM",

    # Authorisation
    "AUTHZ_DENIED":              "MEDIUM",      # user tried something they can't do
    "AUTHZ_ROLE_ESCALATION":     "CRITICAL",

    # Data access
    "WATCHLIST_ACCESSED":        "LOW",
    "WATCHLIST_MODIFIED":        "HIGH",
    "INVESTIGATION_PLATE":       "MEDIUM",
    "INVESTIGATION_PERSON":      "HIGH",        # biometric search
    "EVIDENCE_ACCESSED":         "MEDIUM",
    "ALERT_ACKNOWLEDGED":        "LOW",
    "ALERT_RESOLVED":            "LOW",

    # System
    "CAMERA_REGISTRY_IMPORT":    "MEDIUM",
    "CAMERA_MODIFIED":           "MEDIUM",
    "USER_CREATED":              "HIGH",
    "USER_MODIFIED":             "HIGH",
    "USER_DELETED":              "CRITICAL",
    "CONFIG_CHANGED":            "HIGH",

    # Security anomalies
    "RATE_LIMIT_EXCEEDED":       "MEDIUM",
    "INVALID_FILE_UPLOAD":       "MEDIUM",
    "SSRF_ATTEMPT":              "CRITICAL",
    "INJECTION_ATTEMPT":         "CRITICAL",
    "PATH_TRAVERSAL_ATTEMPT":    "CRITICAL",
}

async def security_audit(
    event_type: str,
    actor: str,
    message: str,
    request: Request = None,
    payload: dict = None,
    db = None,
):
    severity = SECURITY_EVENTS.get(event_type, "MEDIUM")

    entry = {
        "event_type":  event_type,
        "severity":    severity,
        "actor":       actor,
        "message":     message,
        "ip_address":  request.client.host if request else None,
        "user_agent":  (request.headers.get("user-agent", "")[:200] if request else None),
        "request_id":  request.headers.get("x-request-id") if request else None,
        "payload_json": json.dumps(sanitise_log_payload(payload or {})),
        "created_at":  datetime.now(timezone.utc),
    }

    # CRITICAL events: log synchronously and alert
    if severity == "CRITICAL":
        logger.critical(f"[SECURITY] {event_type}: {message}")
        # Could trigger notification to admin here

    if db:
        await db.execute(insert(AuditEvent).values(**entry))
        await db.commit()
```

### 9.2 — Anomaly Detection Rules

Run these checks periodically (every 5 minutes via background task):

```python
# api/tasks/security_monitor.py

ANOMALY_RULES = [
    {
        "name": "Brute force from single IP",
        "query": """
            SELECT ip_address, COUNT(*) as attempts
            FROM audit_events
            WHERE event_type = 'AUTH_LOGIN_FAILURE'
            AND created_at > NOW() - INTERVAL '5 minutes'
            GROUP BY ip_address
            HAVING COUNT(*) > 10
        """,
        "severity": "HIGH",
    },
    {
        "name": "Unusual investigation volume",
        "query": """
            SELECT actor, COUNT(*) as count
            FROM audit_events
            WHERE event_type IN ('INVESTIGATION_PLATE', 'INVESTIGATION_PERSON')
            AND created_at > NOW() - INTERVAL '1 hour'
            GROUP BY actor
            HAVING COUNT(*) > 100
        """,
        "severity": "HIGH",
    },
    {
        "name": "Watchlist access outside business hours",
        "query": """
            SELECT actor, created_at
            FROM audit_events
            WHERE event_type IN ('WATCHLIST_ACCESSED', 'WATCHLIST_MODIFIED')
            AND EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Kolkata')
                NOT BETWEEN 6 AND 22
            AND created_at > NOW() - INTERVAL '5 minutes'
        """,
        "severity": "MEDIUM",
    },
    {
        "name": "Admin privilege actions by non-admin",
        "query": """
            SELECT ae.actor, u.role, ae.event_type
            FROM audit_events ae
            JOIN users u ON u.username = ae.actor
            WHERE ae.event_type IN ('USER_CREATED','USER_DELETED','CONFIG_CHANGED')
            AND u.role NOT IN ('admin', 'superadmin')
            AND ae.created_at > NOW() - INTERVAL '5 minutes'
        """,
        "severity": "CRITICAL",
    },
]
```

---

## Layer 10: Security Implementation Priority

Run in this exact order. Each layer gates the next in terms of risk reduction per engineering hour:

```
SPRINT 1 — Authentication Hardening (highest impact)
│
├── [ ] Short-lived JWT (15min access, 8hr refresh)
├── [ ] Refresh token rotation with revocation list
├── [ ] Password policy enforcement backend (not just frontend)
├── [ ] Rate limiting on auth endpoints (5/minute login)
├── [ ] JWT_SECRET_KEY + JWT_REFRESH_SECRET_KEY to separate secrets
└── [ ] Remove any hardcoded dev secrets from docker-compose.yml

SPRINT 2 — Input Validation (second highest impact)
│
├── [ ] Pydantic validators on all request models
├── [ ] SSRF protection on all URL-accepting endpoints
├── [ ] File upload MIME validation using magic bytes
├── [ ] Frontend ValidatedInput component deployed on all forms
├── [ ] Path traversal guards on evidence/storage routes
└── [ ] SQL query audit: zero string interpolation in queries

SPRINT 3 — Transport and Application Security
│
├── [ ] CSP header (strict, nonce-based for scripts)
├── [ ] DOMPurify on all API data rendered in DOM
├── [ ] CORS locked to explicit origin allowlist
├── [ ] Request size limits middleware
├── [ ] CSRF standardised across all mutating endpoints
└── [ ] Security headers on every response

SPRINT 4 — Container and Infrastructure
│
├── [ ] All Dockerfiles: non-root users, drop capabilities
├── [ ] Docker Compose: read-only filesystems, resource limits
├── [ ] Network segregation: internal network for DB/Redis
├── [ ] Secrets via environment only (.env.example committed, .env gitignored)
├── [ ] Database user privilege separation (app vs migration vs readonly)
└── [ ] Redis password enforced

SPRINT 5 — Monitoring and Hardening
│
├── [ ] Security audit logging for all events in taxonomy
├── [ ] Credential scrubber on all log output
├── [ ] Anomaly detection background task
├── [ ] Biometric field encryption at rest
├── [ ] Token revocation cleanup job (expired entries)
└── [ ] Security event escalation for CRITICAL severity
```