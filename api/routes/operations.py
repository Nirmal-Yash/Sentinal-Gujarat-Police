from datetime import datetime, timezone
import os
import uuid

import redis as redis_lib
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import Principal, require_permission
from database import get_db

router = APIRouter(prefix="/operations", tags=["operations"])
REDIS_URL = __import__("os").getenv("REDIS_URL", "redis://localhost:6379")
AI_HEALTH_PREFIX = __import__("os").getenv("AI_HEALTH_PREFIX", "sentinel:ai:health:")
AI_HEALTH_STALE_SECS = max(10, int(__import__("os").getenv("AI_HEALTH_STALE_SECS", "45")))


def _redis_health():
    result = {"available": False, "production": {"processes": [], "streams": {}}, "test": {"processes": [], "streams": {}}}
    test_prefix = os.getenv("TEST_AI_HEALTH_PREFIX", "sentinel:ai:health:test:")
    try:
        client = redis_lib.from_url(REDIS_URL, decode_responses=True, socket_timeout=1, socket_connect_timeout=1)
        client.ping()
        result["available"] = True
        runtime_mode = client.get("sentinel:runtime:mode") or "production"
        result["runtime_mode"] = runtime_mode
        for key in sorted(client.scan_iter(match=AI_HEALTH_PREFIX + "*")):
            if key.startswith(test_prefix):
                continue
            item = client.hgetall(key)
            if not item:
                continue
            heartbeat = float(item.get("heartbeat_at", "0") or 0)
            item["stale"] = max(0.0, datetime.now(timezone.utc).timestamp() - heartbeat) > AI_HEALTH_STALE_SECS
            result["production"]["processes"].append(item)
        for key in sorted(client.scan_iter(match=test_prefix + "*")):
            item = client.hgetall(key)
            if not item:
                continue
            heartbeat = float(item.get("heartbeat_at", "0") or 0)
            item["stale"] = max(0.0, datetime.now(timezone.utc).timestamp() - heartbeat) > AI_HEALTH_STALE_SECS
            result["test"]["processes"].append(item)
        for stream in ("raw_frames", "detections", "anpr_requests", "alerts"):
            try:
                result["production"]["streams"][stream] = {"length": int(client.xlen(stream))}
            except Exception:
                result["production"]["streams"][stream] = {"length": None}
        for stream in ("test:raw_frames", "test:detections", "test:alerts"):
            try:
                result["test"]["streams"][stream] = {"length": int(client.xlen(stream))}
            except Exception:
                result["test"]["streams"][stream] = {"length": None}
    except Exception as exc:
        result["error"] = type(exc).__name__
    return result


@router.get("/cameras/{camera_id}/health")
async def camera_health_history(camera_id: uuid.UUID, minutes: int = Query(60, ge=5, le=10080), _: Principal = Depends(require_permission("camera:read")), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""SELECT observed_at, health_status, source_fps, decode_fps, published_fps, reconnect_count, decode_failure_count
        FROM camera_health_observations WHERE camera_id=CAST(:camera_id AS uuid) AND observed_at >= NOW() - (CAST(:minutes AS integer) * INTERVAL '1 minute') ORDER BY observed_at ASC"""), {"camera_id": str(camera_id), "minutes": minutes})
    return {"camera_id": str(camera_id), "minutes": minutes, "observations": [dict(row) for row in result.mappings()]}


@router.get("/cameras/health/summary")
async def camera_health_summary(_: Principal = Depends(require_permission("camera:read")), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT health_status, COUNT(*) AS cameras FROM cameras WHERE status <> 'deleted' GROUP BY health_status ORDER BY health_status"))
    return {"items": [dict(row) for row in result.mappings()]}


@router.get("/overview")
async def operations_overview(_: Principal = Depends(require_permission("report:read")), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted') AS cameras_total,
               (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted' AND health_status='healthy') AS cameras_healthy,
               (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted' AND health_status IN ('reconnecting','degraded')) AS cameras_degraded,
               (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted' AND health_status='offline') AS cameras_offline,
               (SELECT COUNT(*) FROM cameras WHERE status <> 'deleted' AND last_frame_at >= NOW() - INTERVAL '30 seconds') AS cameras_recent_frame,
               (SELECT COUNT(*) FROM detections WHERE timestamp >= NOW() - INTERVAL '5 minutes') AS detections_5m,
               (SELECT COUNT(*) FROM vehicle_sightings WHERE source_timestamp >= NOW() - INTERVAL '5 minutes') AS sightings_5m,
               (SELECT COUNT(*) FROM alerts WHERE status='NEW') AS alerts_new,
               (SELECT COUNT(*) FROM alerts WHERE created_at >= NOW() - INTERVAL '1 hour') AS alerts_1h,
               (SELECT COUNT(*) FROM vehicle_journeys WHERE status='ACTIVE') AS active_journeys,
               (SELECT COUNT(*) FROM evidence WHERE created_at >= NOW() - INTERVAL '1 hour' AND COALESCE((metadata->>'test')::boolean, false) = false) AS evidence_1h
    """)).mappings().one()
    runtime = _redis_health()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": dict(result),
        "runtime": {
            "redis": {"available": runtime["available"]},
            "mode": runtime.get("runtime_mode", "production"),
            "production": runtime.get("production", {}),
            "test": runtime.get("test", {}),
        },
    }


@router.get("/audit/verify")
async def verify_audit_chain(_: Principal = Depends(require_permission("audit:read")), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT audit_seq, valid FROM verify_camera_audit_chain() ORDER BY audit_seq"))
    rows = [dict(row) for row in result.mappings()]
    return {"valid": all(bool(row["valid"]) for row in rows), "entries": len(rows), "invalid_entries": [row["audit_seq"] for row in rows if not row["valid"]], "checked_at": datetime.now(timezone.utc).isoformat()}
