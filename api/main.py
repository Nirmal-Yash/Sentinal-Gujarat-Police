#!/usr/bin/env python3
"""Sentinel AI FastAPI backend."""
import asyncio, os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Session
from auth import AUTH_REQUIRED, principal_from_token
from websocket_manager import manager, redis_alert_consumer
from routes import cameras, alerts, watchlist, search, auth, reports, test, vendors, evidence
from migrations import apply_migrations

logging.basicConfig(level=logging.INFO, format="%(asctime)s [API][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]

@asynccontextmanager
async def lifespan(app: FastAPI):
    apply_migrations()
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

@app.get("/")
async def root():
    return {"service": "Sentinel AI API", "docs": "/docs", "ws": "/ws/alerts", "version": "1.0.0"}
