#!/usr/bin/env python3
"""
Sentinel AI — FastAPI backend
REST API + WebSocket real-time alerts
"""
import asyncio, os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import engine, Base
from websocket_manager import manager, redis_alert_consumer
from routes import cameras, alerts, watchlist, search
from migrations import apply_migrations

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [API][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply additive, versioned schema changes before ORM startup.  This keeps
    # existing Postgres volumes compatible rather than relying on create_all.
    apply_migrations()
    # Legacy tables remain supported while migrations own schema evolution.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Start Redis → WebSocket bridge
    task = asyncio.create_task(redis_alert_consumer())
    log.info("API ready.")
    yield
    task.cancel()
    await engine.dispose()


app = FastAPI(
    title="Sentinel AI — Gujarat Police Innovation Challenge",
    version="1.0.0",
    description="AI-powered multi-camera surveillance platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── REST Routers ─────────────────────────────────────────────────────────────
app.include_router(cameras.router)
app.include_router(alerts.router)
app.include_router(watchlist.router)
app.include_router(search.router)


# ─── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # Keep alive — client can send pings
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "sentinel-ai"}


@app.get("/")
async def root():
    return {
        "service":  "Sentinel AI API",
        "docs":     "/docs",
        "ws":       "/ws/alerts",
        "version":  "1.0.0",
    }
