from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, update, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from models import Alert, AlertOut, Camera
from auth import require_permission, has_permission, Principal
from database import get_db
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import uuid, os, json, logging
import redis as redis_lib

log = logging.getLogger(__name__)
EVIDENCE_ROOT = Path(os.getenv("EVIDENCE_STORAGE_PATH", "/evidence"))
TEST_EVIDENCE_RETENTION_DAYS = max(1, int(os.getenv("TEST_EVIDENCE_RETENTION_DAYS", "7")))

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(require_permission("alert:read"))])
VALID_TRANSITIONS = {"NEW": {"ACKNOWLEDGED"}, "ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"}, "INVESTIGATING": {"RESOLVED"}, "RESOLVED": {"CLOSED"}, "CLOSED": set()}
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_PRIVATE_DETAIL_KEYS = {"dedup_key", "dedup_bucket", "evidence_storage_key", "evidence_sha256", "confidence", "score"}

async def _auto_close_resolved(db: AsyncSession):
    """Close resolved alerts after the retention window, with an audit record."""
    rows = (await db.execute(text("""UPDATE alerts
        SET status='CLOSED', closed_at=NOW(), closed_by='system:auto-close', updated_at=NOW()
        WHERE status='RESOLVED' AND resolved_at IS NOT NULL
          AND resolved_at < NOW() - INTERVAL '30 days'
        RETURNING id"""))).scalars().all()
    if rows:
        for alert_id in rows:
            await db.execute(text("""INSERT INTO alert_audit_log(alert_id,actor,action,from_status,to_status,reason)
                VALUES(:id,'system:auto-close','AUTO_CLOSE','RESOLVED','CLOSED','resolved for more than 30 days')"""), {"id": str(alert_id)})
        await db.commit()


async def _purge_stale_test_evidence(db: AsyncSession):
    """Remove orphaned test evidence files from closed sessions older than retention window."""
    rows = (await db.execute(text("""
        SELECT e.id, e.storage_key, e.metadata->>'thumbnail_key' AS thumbnail_key
        FROM evidence e
        WHERE COALESCE((e.metadata->>'test')::boolean, false) = true
          AND e.created_at < NOW() - (CAST(:days AS integer) * INTERVAL '1 day')
          AND NOT EXISTS (
            SELECT 1 FROM test_sessions s
            WHERE s.id::text = e.metadata->>'session_id'
              AND s.status IN ('starting', 'active')
          )
    """), {"days": TEST_EVIDENCE_RETENTION_DAYS})).mappings().all()
    if not rows:
        return
    removed = 0
    for row in rows:
        for key in (row["storage_key"], row["thumbnail_key"]):
            if not key:
                continue
            target = EVIDENCE_ROOT / str(key)
            try:
                if target.is_file():
                    target.unlink()
                    removed += 1
            except OSError as exc:
                log.warning("Failed to purge test evidence file %s: %s", target, exc)
        await db.execute(text("DELETE FROM evidence WHERE id=CAST(:id AS uuid)"), {"id": str(row["id"])})
    if removed:
        await db.commit()
        log.info("Purged %s stale test evidence file(s)", removed)


def _public_alert(alert, camera):
    details = dict(alert.details or {})
    public_details = {key: value for key, value in details.items() if key not in _PRIVATE_DETAIL_KEYS}
    camera_data = None
    camera_name = None
    if camera:
        camera_name = camera.name
        camera_data = {"id": str(camera.id), "name": camera.name, "location": camera.location or "Location not registered", "coordinates": {"lat": camera.lat, "lng": camera.lng}, "department": camera.department or "Unassigned"}
    else:
        camera_data = None
        camera_name = details.get("camera_label") or details.get("cam_name")
    summary = details.get("human_summary")
    if not summary:
        label = camera_name or "the monitored camera"
        summary = f"{str(alert.alert_type or 'Alert').replace('_', ' ').capitalize()} at {label}."
    evidence = details.get("evidence") or {"available": False, "description": "Evidence frame unavailable."}
    raw_detection_detail = details.get("detection_detail") or {key: value for key, value in public_details.items() if key not in {"human_summary", "evidence"}}
    detection_detail = {key: value for key, value in dict(raw_detection_detail).items() if key not in _PRIVATE_DETAIL_KEYS}
    return {"id": alert.id, "cam_id": alert.cam_id, "cam_name": camera.name if camera else None, "camera_label": camera.name if camera else None, "alert_type": alert.alert_type, "priority": alert.priority, "severity": alert.priority, "entity_type": alert.entity_type, "details": public_details, "acknowledged": alert.acknowledged, "status": alert.status, "created_at": alert.created_at, "updated_at": alert.updated_at, "acknowledged_at": alert.acknowledged_at, "acknowledged_by": alert.acknowledged_by, "resolved_at": alert.resolved_at, "resolved_by": alert.resolved_by, "closed_at": alert.closed_at, "closed_by": alert.closed_by, "human_summary": summary, "camera": camera_data, "detected_at": alert.created_at, "detection_detail": detection_detail, "evidence": evidence}

@router.get("/", response_model=list[AlertOut])
async def list_alerts(
    priority: Optional[str] = None,
    alert_type: Optional[str] = None,
    cam_id: Optional[uuid.UUID] = None,
    camera: Optional[str] = Query(None, max_length=100),
    plate: Optional[str] = Query(None, max_length=20),
    status: Optional[str] = None,
    from_ts: Optional[str] = Query(None, alias="from"),
    to_ts: Optional[str] = Query(None, alias="to"),
    unacked: bool = False,
    limit: int = Query(300, ge=1, le=300),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    await _auto_close_resolved(db)
    await _purge_stale_test_evidence(db)
    clauses = []
    params: dict = {"limit": limit, "offset": offset}
    if priority:
        clauses.append("a.priority = upper(:priority)")
        params["priority"] = priority
    if alert_type:
        clauses.append("a.alert_type ILIKE '%' || :alert_type || '%'")
        params["alert_type"] = alert_type
    if cam_id:
        clauses.append("a.cam_id = CAST(:cam_id AS uuid)")
        params["cam_id"] = str(cam_id)
    if camera:
        clauses.append("(c.name ILIKE :camera OR c.location ILIKE :camera)")
        params["camera"] = f"%{camera.strip()}%"
    if plate:
        clauses.append("COALESCE(a.details->>'plate_text', '') ILIKE :plate")
        params["plate"] = f"%{plate.strip()}%"
    if status:
        clauses.append("a.status = upper(:status)")
        params["status"] = status
    if from_ts:
        clauses.append("a.created_at >= CAST(:from_ts AS timestamptz)")
        params["from_ts"] = from_ts
    if to_ts:
        clauses.append("a.created_at <= CAST(:to_ts AS timestamptz)")
        params["to_ts"] = to_ts
    if unacked:
        clauses.append("a.status = 'NEW'")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await db.execute(text(f"""
        SELECT a.* FROM alerts a
        LEFT JOIN cameras c ON c.id = a.cam_id
        {where_sql}
        ORDER BY a.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params)
    alert_rows = result.mappings().all()
    ids = {row["cam_id"] for row in alert_rows if row.get("cam_id")}
    cameras = (await db.execute(select(Camera).where(Camera.id.in_(ids)))).scalars().all() if ids else []
    by_id = {camera.id: camera for camera in cameras}
    return [_public_alert(SimpleNamespace(**dict(row)), by_id.get(row["cam_id"])) for row in alert_rows]

async def _broadcast_transition(alert: Alert, from_status: str, to_status: str, actor: str, reason: str | None):
    try:
        r = redis_lib.from_url(REDIS_URL, decode_responses=False)
        payload = {
            b"schema_version": b"1.0", b"event_type": b"alert_status_changed", b"alert_id": str(alert.id).encode(), b"id": str(alert.id).encode(),
            b"cam_id": str(alert.cam_id or "").encode(), b"alert_type": str(alert.alert_type).encode(), b"priority": str(alert.priority).encode(),
            b"confidence": str(alert.confidence or 0).encode(), b"entity_type": str(alert.entity_type or "").encode(), b"status": to_status.encode(),
            b"from_status": from_status.encode(), b"actor": actor.encode(), b"reason": (reason or "").encode(), b"event_timestamp": str(datetime.now(timezone.utc).timestamp()).encode(),
            b"details": json.dumps(alert.details or {}).encode()
        }
        r.xadd("alerts", payload, maxlen=10000, approximate=True)
    except Exception:
        pass

async def _transition(alert_id, target, principal, db, reason=None):
    if not principal or not has_permission(principal, "alert:operate"):
        raise HTTPException(status_code=403, detail="Permission required: alert:operate")
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id).with_for_update())).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    current = (alert.status or ("ACKNOWLEDGED" if alert.acknowledged else "NEW")).upper()
    target = target.upper()
    if target == current:
        await db.rollback()
        return {"status": current, "alert_id": str(alert_id), "idempotent": True}
    if target not in VALID_TRANSITIONS.get(current, set()):
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Invalid alert transition: {current} -> {target}")
    now = datetime.now(timezone.utc)
    values = {"status": target, "updated_at": now}
    if target == "ACKNOWLEDGED": values.update(acknowledged=True, acknowledged_at=now, acknowledged_by=principal.username)
    elif target == "INVESTIGATING": values.update(acknowledged=True, acknowledged_at=alert.acknowledged_at or now, acknowledged_by=alert.acknowledged_by or principal.username)
    elif target == "RESOLVED": values.update(resolved_at=now, resolved_by=principal.username)
    elif target == "CLOSED": values.update(closed_at=now, closed_by=principal.username)
    await db.execute(update(Alert).where(Alert.id == alert_id).values(**values))
    await db.execute(text("INSERT INTO alert_audit_log(alert_id, actor, action, from_status, to_status, reason) VALUES (:id,:actor,'STATUS_CHANGE',:frm,:to,:reason)"), {"id": str(alert_id), "actor": principal.username, "frm": current, "to": target, "reason": reason})
    await db.commit()
    alert.status = target
    alert.updated_at = now
    await _broadcast_transition(alert, current, target, principal.username, reason)
    return {"status": target, "alert_id": str(alert_id), "actor": principal.username, "idempotent": False}

@router.post("/{alert_id}/acknowledge")
async def acknowledge(alert_id: uuid.UUID, principal: Principal = Depends(require_permission("alert:operate")), db: AsyncSession = Depends(get_db)):
    return await _transition(alert_id, "ACKNOWLEDGED", principal, db)

@router.post("/{alert_id}/transition")
async def transition_alert(alert_id: uuid.UUID, target_status: str = Query(..., min_length=3, max_length=32), reason: Optional[str] = Query(None, max_length=1000), principal: Principal = Depends(require_permission("alert:operate")), db: AsyncSession = Depends(get_db)):
    return await _transition(alert_id, target_status, principal, db, reason)

@router.get("/stats/counts")
async def alert_counts(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("alert:read"))):
    await _auto_close_resolved(db)
    await _purge_stale_test_evidence(db)
    result = await db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE priority = 'CRITICAL') AS critical,
               COUNT(*) FILTER (WHERE priority = 'HIGH') AS high,
               COUNT(*) FILTER (WHERE priority = 'MEDIUM') AS medium,
               COUNT(*) FILTER (WHERE priority = 'LOW') AS low,
               COUNT(*) FILTER (WHERE status = 'NEW') AS new,
               COUNT(*) FILTER (WHERE status = 'ACKNOWLEDGED') AS acknowledged,
               COUNT(*) FILTER (WHERE status = 'INVESTIGATING') AS investigating,
               COUNT(*) FILTER (WHERE status = 'RESOLVED') AS resolved,
               COUNT(*) FILTER (WHERE status = 'CLOSED') AS closed,
               COUNT(*) FILTER (WHERE status = 'NEW') AS unacknowledged,
               COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') AS last_hour
        FROM alerts"""))
    return dict(result.mappings().one())
