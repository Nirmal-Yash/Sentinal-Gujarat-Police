"""Small Redis-backed health registry for AI child processes."""
from __future__ import annotations

import os
import time
from typing import Optional

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
KEY_PREFIX = os.getenv("AI_HEALTH_PREFIX", "sentinel:ai:health:")
TTL = max(15, int(os.getenv("AI_HEALTH_TTL_SECS", "45")))


def _client():
    return redis.from_url(REDIS_URL, decode_responses=True)


def publish(name: str, status: str, pid: Optional[int] = None, restart_count: int = 0, started_at: Optional[float] = None, exit_code: Optional[int] = None) -> None:
    payload = {
        "name": name,
        "status": status,
        "pid": str(pid or ""),
        "restart_count": str(restart_count),
        "started_at": str(started_at or time.time()),
        "heartbeat_at": str(time.time()),
        "exit_code": "" if exit_code is None else str(exit_code),
    }
    try:
        r = _client()
        r.hset(KEY_PREFIX + name, mapping=payload)
        r.expire(KEY_PREFIX + name, TTL)
    except Exception:
        pass


def heartbeat(name: str, pid: Optional[int], restart_count: int, started_at: float) -> None:
    publish(name, "RUNNING", pid, restart_count, started_at)
