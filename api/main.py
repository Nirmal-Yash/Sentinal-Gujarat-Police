#!/usr/bin/env python3
"""Sentinel AI FastAPI backend."""
import asyncio, os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, Session, get_db
from auth import AUTH_REQUIRED, SECRET_KEY, principal_from_token
from websocket_manager import manager, redis_alert_consumer
from routes import cameras, alerts, watchlist, search, auth, reports, test, vendors, evidence
from migrations import apply_migrations

logging.basicConfig(level=logging.INFO, format="%(asctime)s [API][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

@asynccontextmanager
async def lifespan(app: FastAPI):
    apply_migrations()
    if AUTH_REQUIRED and (not SECRET_KEY or SECRET_KEY == "sentinel-change-in-production"):
        raise RuntimeError("AUTH_REQUIRED=true requires a non-default SECRET_KEY")
    task = asyncio.create_task(redis_alert_consumer())
    log.info("API ready; schema owned by versioned migrations.")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await engine.dispose()

app = FastAPI(title="Sentinel AI — Gujarat Police Innovation Challenge", version="1.0.0",
              description="AI-powered multi-camera surveillance platform", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(cameras.router); app.include_router(alerts.router); app.include_router(watchlist.router); app.include_router(search.router)
app.include_router(auth.router); app.include_router(reports.router); app.include_router(test.router); app.include_router(vendors.router); app.include_router(evidence.router)

@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    if AUTH_REQUIRED:
        token = ws.query_params.get("access_token")
        if not token:
            await ws.close(code=1008); return
        try:
            async with Session() as db:
                await principal_from_token(token, db)
        except Exception:
            await ws.close(code=1008); return
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "sentinel-ai"}

@app.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    """Dependency readiness: return 503 until DB and Redis respond."""
    checks = {"database": False, "redis": False}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        log.warning("Readiness database check failed: %s", exc)
    try:
        import redis as redis_lib
        def ping_redis():
            client = redis_lib.from_url(REDIS_URL, decode_responses=True)
            try:
                return bool(client.ping())
            finally:
                try: client.close()
                except Exception: pass
        checks["redis"] = await asyncio.to_thread(ping_redis)
    except Exception as exc:
        log.warning("Readiness Redis check failed: %s", exc)
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}

@app.get("/")
async def root():
    return {"service": "Sentinel AI API", "docs": "/docs", "ws": "/ws/alerts", "version": "1.0.0"}
