"""WebSocket manager — broadcasts real-time alerts from Redis stream to all clients."""
import asyncio, json, logging, os, uuid
from typing import Set
from fastapi import WebSocket
import redis.asyncio as aioredis

log      = logging.getLogger("ws_manager")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM    = "alerts"
GROUP     = "api_ws"


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        log.info(f"WS connected ({len(self.active)} total)")

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        log.info(f"WS disconnected ({len(self.active)} total)")

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active.discard(ws)


manager = ConnectionManager()


async def redis_alert_consumer():
    """Background task: consume Redis 'alerts' stream → broadcast to WS clients."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)

    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception:
        pass   # group already exists

    consumer = f"api-ws-{uuid.uuid4().hex[:8]}"
    log.info("Redis alert consumer started.")

    while True:
        try:
            msgs = await r.xreadgroup(GROUP, consumer,
                                      {STREAM: ">"}, count=20, block=500)
            if not msgs:
                await asyncio.sleep(0.05)
                continue

            for _, entries in msgs:
                for msg_id, data in entries:
                    try:
                        payload = {
                            "type":        "alert",
                            "alert_id":    data.get("alert_id", ""),
                            "id":           data.get("id") or data.get("alert_id", ""),
                            "cam_id":      data.get("cam_id", ""),
                            "alert_type":  data.get("alert_type", ""),
                            "priority":    data.get("priority", "MEDIUM"),
                            "confidence":  float(data.get("confidence", 0)),
                            "entity_type": data.get("entity_type", ""),
                            "details":     json.loads(data.get("details", "{}")),
                            "timestamp":   data.get("timestamp", ""),
                        }
                        if manager.active:
                            await manager.broadcast(payload)
                        await r.xack(STREAM, GROUP, msg_id)
                    except Exception as e:
                        log.error(f"Alert parse error: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Consumer error: {e}")
            await asyncio.sleep(2)
