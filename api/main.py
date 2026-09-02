#!/usr/bin/env python3
"""Sentinel AI FastAPI backend."""
import asyncio, os, logging, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, Session, get_db
from auth import AUTH_REQUIRED, SECRET_KEY, REFRESH_SECRET, principal_from_token, hash_password
from websocket_manager import manager, redis_alert_consumer
from routes import cameras, camera_snapshot, camera_imports, alerts, watchlist, search, auth, reports, test, vendors, evidence, evidence_assets, operations, test_alerts, cctv
from migrations import apply_migrations
from security_hardening import SecurityHeadersMiddleware, RequestSizeLimitMiddleware, SecurityAuditMiddleware, verify_cookie_csrf
logging.basicConfig(level=logging.INFO, format="%(asctime)s [API][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
CORS_ORIGINS=[x.strip() for x in os.getenv("ALLOWED_ORIGINS",os.getenv("CORS_ORIGINS","http://localhost:3000")).split(",") if x.strip()]
REDIS_URL=os.getenv("REDIS_URL","redis://localhost:6379")
BOOTSTRAP_ADMIN_USERNAME=os.getenv("BOOTSTRAP_ADMIN_USERNAME","").strip(); BOOTSTRAP_ADMIN_PASSWORD=os.getenv("BOOTSTRAP_ADMIN_PASSWORD",""); BOOTSTRAP_ADMIN_ROLE=os.getenv("BOOTSTRAP_ADMIN_ROLE","SUPERADMIN").upper()
STARTUP_RETRIES=max(1,int(os.getenv("STARTUP_RETRIES","30"))); STARTUP_RETRY_DELAY=max(1.0,float(os.getenv("STARTUP_RETRY_DELAY","2")))
INSECURE_SECRET_VALUES={"","change-me","changeme","sentinel-change-in-production","replace-me","replace-with-long-random-secret","ci-only-sentinel-signing-secret","ci-only-snapshot-signing-secret"}
async def bootstrap_admin(db:AsyncSession)->None:
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),{"lock_key":"sentinel:bootstrap-admin:v1"})
    active=await db.scalar(text("SELECT 1 FROM users WHERE role IN ('ADMIN','SUPERADMIN') AND is_active=TRUE LIMIT 1"))
    if active:return
    if not BOOTSTRAP_ADMIN_USERNAME or not BOOTSTRAP_ADMIN_PASSWORD:
        if AUTH_REQUIRED:raise RuntimeError("No active ADMIN/SUPERADMIN exists and bootstrap admin credentials are not configured")
        return
    if BOOTSTRAP_ADMIN_ROLE not in {"ADMIN","SUPERADMIN"}:raise RuntimeError("BOOTSTRAP_ADMIN_ROLE must be ADMIN or SUPERADMIN")
    password_hash=hash_password(BOOTSTRAP_ADMIN_PASSWORD)
    existing=await db.scalar(text("SELECT 1 FROM users WHERE username=:username LIMIT 1"),{"username":BOOTSTRAP_ADMIN_USERNAME})
    if existing: await db.execute(text("UPDATE users SET password_hash=:password_hash,role=:role,is_active=TRUE WHERE username=:username"),{"username":BOOTSTRAP_ADMIN_USERNAME,"password_hash":password_hash,"role":BOOTSTRAP_ADMIN_ROLE})
    else: await db.execute(text("INSERT INTO users(username,password_hash,role,is_active) VALUES(:username,:password_hash,:role,TRUE)"),{"username":BOOTSTRAP_ADMIN_USERNAME,"password_hash":password_hash,"role":BOOTSTRAP_ADMIN_ROLE})
    await db.commit()
async def initialize_runtime()->None:
    last=None
    for attempt in range(1,STARTUP_RETRIES+1):
        try:
            apply_migrations()
            if AUTH_REQUIRED and (SECRET_KEY or "").strip().lower() in INSECURE_SECRET_VALUES: raise RuntimeError("AUTH_REQUIRED=true requires a strong non-placeholder SECRET_KEY")
            if AUTH_REQUIRED and ((not REFRESH_SECRET) or REFRESH_SECRET.lower() in INSECURE_SECRET_VALUES or REFRESH_SECRET==SECRET_KEY): raise RuntimeError("AUTH_REQUIRED=true requires JWT_REFRESH_SECRET_KEY distinct from SECRET_KEY")
            snap=(os.getenv("SNAPSHOT_TOKEN_SECRET","") or "").strip()
            if not snap or snap.lower() in INSECURE_SECRET_VALUES: raise RuntimeError("SNAPSHOT_TOKEN_SECRET must be supplied and must not be a placeholder")
            if os.getenv("ENVIRONMENT","development").lower()=="production":
                if not os.getenv("FIELD_ENCRYPTION_KEY","").strip(): raise RuntimeError("FIELD_ENCRYPTION_KEY must be configured in production")
                if os.getenv("DB_SSL","0").lower() not in {"1","true","require"}: raise RuntimeError("DB_SSL must be enabled in production")
                if os.getenv("AUTH_COOKIE_SECURE","false").lower()!="true": raise RuntimeError("AUTH_COOKIE_SECURE=true is required in production")
            async with Session() as db: await bootstrap_admin(db)
            return
        except Exception as exc:
            last=exc
            if attempt>=STARTUP_RETRIES: raise
            log.warning("Startup dependency check failed (%s/%s): %s; retrying in %.1fs",attempt,STARTUP_RETRIES,exc,STARTUP_RETRY_DELAY); await asyncio.sleep(STARTUP_RETRY_DELAY)
    raise last or RuntimeError("API startup initialization failed")
@asynccontextmanager
async def lifespan(app:FastAPI):
    await initialize_runtime(); task=asyncio.create_task(redis_alert_consumer()); yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
    await engine.dispose()
app=FastAPI(title="Sentinel AI — Gujarat Police Innovation Challenge",version="1.0.0",description="AI-powered multi-camera surveillance platform",lifespan=lifespan)
app.add_middleware(RequestSizeLimitMiddleware); app.add_middleware(SecurityHeadersMiddleware); app.add_middleware(SecurityAuditMiddleware)
app.add_middleware(CORSMiddleware,allow_origins=CORS_ORIGINS,allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type","X-Test-Session-Id","X-CSRF-Token"],expose_headers=["X-Request-Id"],max_age=600)
@app.middleware("http")
async def csrf_boundary(request:Request,call_next):
    if request.method.upper() not in {"GET","HEAD","OPTIONS"} and request.url.path not in {"/auth/login","/auth/refresh"}:
        if not request.headers.get("Authorization","").startswith("Bearer ") and request.cookies.get("sentinel_session"): verify_cookie_csrf(request,request.cookies.get("sentinel_csrf"))
    response=await call_next(request); response.headers.setdefault("X-Request-Id",str(uuid.uuid4())); return response
app.include_router(camera_snapshot.router); app.include_router(cameras.router); app.include_router(camera_imports.router); app.include_router(cctv.router); app.include_router(alerts.router); app.include_router(watchlist.router); app.include_router(search.router); app.include_router(auth.router); app.include_router(reports.router); app.include_router(test.router); app.include_router(test_alerts.router); app.include_router(vendors.router); app.include_router(evidence_assets.router); app.include_router(evidence.router); app.include_router(operations.router)
@app.websocket("/ws/alerts")
async def ws_alerts(ws:WebSocket):
    if AUTH_REQUIRED:
        token=ws.query_params.get("access_token")
        if not token: await ws.close(code=1008); return
        try:
            async with Session() as db: await principal_from_token(token,db)
        except Exception: await ws.close(code=1008); return
    await manager.connect(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: manager.disconnect(ws)
@app.get("/health")
async def health(): return {"status":"ok","service":"sentinel-ai"}
@app.get("/ready")
async def ready(db:AsyncSession=Depends(get_db)):
    checks={"database":False,"redis":False,"authentication":False,"snapshot_signing":False,"field_encryption":False}
    try: await db.execute(text("SELECT 1")); checks["database"]=True
    except Exception: pass
    try: checks["authentication"]=(not AUTH_REQUIRED) or bool(await db.scalar(text("SELECT 1 FROM users WHERE role IN ('ADMIN','SUPERADMIN') AND is_active=TRUE LIMIT 1")))
    except Exception: pass
    try:
        import redis as redis_lib
        def ping():
            c=redis_lib.from_url(REDIS_URL,decode_responses=True)
            try:return bool(c.ping())
            finally:
                try:c.close()
                except Exception:pass
        checks["redis"]=await asyncio.to_thread(ping)
    except Exception: pass
    snap=(os.getenv("SNAPSHOT_TOKEN_SECRET","") or "").strip(); checks["snapshot_signing"]=bool(snap) and snap.lower() not in INSECURE_SECRET_VALUES
    checks["field_encryption"]=bool(os.getenv("FIELD_ENCRYPTION_KEY","").strip()) or os.getenv("ENVIRONMENT","development").lower()!="production"
    if not all(checks.values()): raise HTTPException(503,detail={"status":"not_ready","checks":checks})
    return {"status":"ready","checks":checks}
@app.get("/")
async def root(): return {"service":"Sentinel AI API","docs":"/docs","ws":"/ws/alerts","version":"1.0.0"}
