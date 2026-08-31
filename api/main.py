#!/usr/bin/env python3
"""Sentinel AI FastAPI backend."""
import asyncio, os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, Session, get_db
from auth import AUTH_REQUIRED, SECRET_KEY, principal_from_token, hash_password
from websocket_manager import manager, redis_alert_consumer
from routes import cameras, camera_imports, alerts, watchlist, search, auth, reports, test, vendors, evidence, operations, test_alerts, cctv
from migrations import apply_migrations
logging.basicConfig(level=logging.INFO, format="%(asctime)s [API][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
BOOTSTRAP_ADMIN_ROLE = os.getenv("BOOTSTRAP_ADMIN_ROLE", "SUPERADMIN").upper()
BOOTSTRAP_LOCK_KEY = "sentinel:bootstrap-admin:v1"
STARTUP_RETRIES = max(1, int(os.getenv("STARTUP_RETRIES", "30")))
STARTUP_RETRY_DELAY = max(1.0, float(os.getenv("STARTUP_RETRY_DELAY", "2")))

async def bootstrap_admin(db: AsyncSession) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": BOOTSTRAP_LOCK_KEY})
    active_admin = await db.scalar(text("SELECT 1 FROM users WHERE role IN ('ADMIN','SUPERADMIN') AND is_active=TRUE LIMIT 1"))
    if active_admin: return
    if not BOOTSTRAP_ADMIN_USERNAME or not BOOTSTRAP_ADMIN_PASSWORD:
        if AUTH_REQUIRED: raise RuntimeError("No active ADMIN/SUPERADMIN exists and bootstrap admin credentials are not configured")
        return
    if BOOTSTRAP_ADMIN_ROLE not in {"ADMIN", "SUPERADMIN"}: raise RuntimeError("BOOTSTRAP_ADMIN_ROLE must be ADMIN or SUPERADMIN")
    password_hash = hash_password(BOOTSTRAP_ADMIN_PASSWORD)
    existing_username = await db.scalar(text("SELECT 1 FROM users WHERE username=:username LIMIT 1"), {"username": BOOTSTRAP_ADMIN_USERNAME})
    if existing_username:
        await db.execute(text("UPDATE users SET password_hash=:password_hash, role=:role, is_active=TRUE WHERE username=:username"), {"username": BOOTSTRAP_ADMIN_USERNAME, "password_hash": password_hash, "role": BOOTSTRAP_ADMIN_ROLE})
    else:
        await db.execute(text("INSERT INTO users(username,password_hash,role,is_active) VALUES(:username,:password_hash,:role,TRUE)"), {"username": BOOTSTRAP_ADMIN_USERNAME, "password_hash": password_hash, "role": BOOTSTRAP_ADMIN_ROLE})
    await db.commit(); log.info("Bootstrap administrative account ready: %s (%s)", BOOTSTRAP_ADMIN_USERNAME, BOOTSTRAP_ADMIN_ROLE)

async def initialize_runtime() -> None:
    last_error = None
    for attempt in range(1, STARTUP_RETRIES + 1):
        try:
            apply_migrations()
            if AUTH_REQUIRED and (not SECRET_KEY or SECRET_KEY == "sentinel-change-in-production"): raise RuntimeError("AUTH_REQUIRED=true requires a non-default SECRET_KEY")
            async with Session() as db: await bootstrap_admin(db)
            log.info("API startup dependencies ready on attempt %s/%s.", attempt, STARTUP_RETRIES); return
        except Exception as exc:
            last_error = exc
            if attempt >= STARTUP_RETRIES: raise
            log.warning("API startup dependency check failed (%s/%s): %s; retrying in %.1fs", attempt, STARTUP_RETRIES, exc, STARTUP_RETRY_DELAY); await asyncio.sleep(STARTUP_RETRY_DELAY)
    raise last_error or RuntimeError("API startup initialization failed")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_runtime(); task = asyncio.create_task(redis_alert_consumer()); log.info("API ready; schema owned by versioned migrations."); yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
    await engine.dispose()

app = FastAPI(title="Sentinel AI — Gujarat Police Innovation Challenge", version="1.0.0", description="AI-powered multi-camera surveillance platform", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(cameras.router); app.include_router(camera_imports.router); app.include_router(cctv.router); app.include_router(alerts.router); app.include_router(watchlist.router); app.include_router(search.router)
app.include_router(auth.router); app.include_router(reports.router); app.include_router(test.router); app.include_router(test_alerts.router); app.include_router(vendors.router); app.include_router(evidence.router); app.include_router(operations.router)

@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    if AUTH_REQUIRED:
        token = ws.query_params.get("access_token")
        if not token: await ws.close(code=1008); return
        try:
            async with Session() as db: await principal_from_token(token, db)
        except Exception: await ws.close(code=1008); return
    await manager.connect(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: manager.disconnect(ws)

@app.get("/health")
async def health(): return {"status": "ok", "service": "sentinel-ai"}

@app.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    checks = {"database": False, "redis": False, "authentication": False}
    try: await db.execute(text("SELECT 1")); checks["database"] = True
    except Exception as exc: log.warning("Readiness database check failed: %s", exc)
    try:
        row = await db.scalar(text("SELECT 1 FROM users WHERE role IN ('ADMIN','SUPERADMIN') AND is_active=TRUE LIMIT 1")); checks["authentication"] = (not AUTH_REQUIRED) or bool(row)
    except Exception as exc: log.warning("Readiness authentication check failed: %s", exc)
    try:
        import redis as redis_lib
        def ping_redis():
            client = redis_lib.from_url(REDIS_URL, decode_responses=True)
            try: return bool(client.ping())
            finally:
                try: client.close()
                except Exception: pass
        checks["redis"] = await asyncio.to_thread(ping_redis)
    except Exception as exc: log.warning("Readiness Redis check failed: %s", exc)
    if not all(checks.values()): raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}

@app.get("/")
async def root(): return {"service": "Sentinel AI API", "docs": "/docs", "ws": "/ws/alerts", "version": "1.0.0"}
