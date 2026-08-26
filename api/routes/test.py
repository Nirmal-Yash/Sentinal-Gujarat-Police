"""Isolated synthetic analytics diagnostics; never touches production streams or tables."""
import json, os, uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis as redis_lib
from database import get_db
from auth import AUTH_REQUIRED, require_role, Principal

router = APIRouter(prefix="/test", tags=["test"])

def enabled():
    if os.getenv("TEST_ENDPOINT_ENABLED", "false").lower() != "true":
        raise HTTPException(404, "Synthetic diagnostics are disabled")
    if not AUTH_REQUIRED:
        raise HTTPException(503, "Synthetic diagnostics require AUTH_REQUIRED=true")

class TestSessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

class SyntheticEvent(BaseModel):
    camera_label: str = Field(min_length=1, max_length=255)
    detection_type: str = Field(default="plate", max_length=50)
    plate_text: str | None = Field(default=None, max_length=100)
    confidence: float = Field(default=0.9, ge=0, le=1)
    create_alert: bool = True

@router.post("/sessions", status_code=201)
async def create_session(body: TestSessionCreate, principal: Principal = Depends(require_role("SUPERADMIN")), db: AsyncSession = Depends(get_db)):
    enabled()
    row = (await db.execute(text("INSERT INTO test_sessions(name,created_by) VALUES(:name,:by) RETURNING id,name,status,created_at"), {"name": body.name, "by": principal.username})).mappings().one()
    await db.commit(); return dict(row)

@router.post("/sessions/{session_id}/events", status_code=201)
async def inject_event(session_id: uuid.UUID, body: SyntheticEvent, principal: Principal = Depends(require_role("SUPERADMIN")), db: AsyncSession = Depends(get_db)):
    enabled()
    exists = await db.scalar(text("SELECT 1 FROM test_sessions WHERE id=CAST(:id AS uuid) AND status='active'"), {"id": str(session_id)})
    if not exists: raise HTTPException(404, "Active test session not found")
    detection = (await db.execute(text("""INSERT INTO test_detections(session_id,camera_label,detection_type,plate_text,confidence)
        VALUES(CAST(:session AS uuid),:camera,:kind,:plate,:confidence) RETURNING id,event_at"""), {"session": str(session_id), "camera": body.camera_label, "kind": body.detection_type, "plate": body.plate_text, "confidence": body.confidence})).mappings().one()
    alert = None
    if body.create_alert:
        alert = (await db.execute(text("""INSERT INTO test_alerts(session_id,detection_id,alert_type,priority,details)
            VALUES(CAST(:session AS uuid),CAST(:detection AS uuid),'synthetic_detection','LOW',CAST(:details AS jsonb)) RETURNING id"""), {"session": str(session_id), "detection": str(detection["id"]), "details": json.dumps({"synthetic": True})})).scalar_one()
    await db.commit()
    redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True).xadd(f"test:{session_id}:detections", {"detection_id": str(detection["id"]), "synthetic": "true"}, maxlen=1000)
    return {"detection_id": str(detection["id"]), "alert_id": str(alert) if alert else None, "namespace": f"test:{session_id}"}

@router.get("/sessions/{session_id}/status")
async def session_status(session_id: uuid.UUID, _: Principal = Depends(require_role("SUPERADMIN")), db: AsyncSession = Depends(get_db)):
    enabled()
    row = (await db.execute(text("""SELECT s.id,s.name,s.status,s.created_at,
      (SELECT COUNT(*) FROM test_detections d WHERE d.session_id=s.id) AS detections,
      (SELECT COUNT(*) FROM test_alerts a WHERE a.session_id=s.id) AS alerts
      FROM test_sessions s WHERE s.id=CAST(:id AS uuid)"""), {"id": str(session_id)})).mappings().first()
    if not row: raise HTTPException(404, "Test session not found")
    return dict(row)

@router.get("/sessions/{session_id}/results")
async def session_results(session_id: uuid.UUID, _: Principal = Depends(require_role("SUPERADMIN")), db: AsyncSession = Depends(get_db)):
    enabled()
    rows = [dict(row) for row in (await db.execute(text("SELECT * FROM test_detections WHERE session_id=CAST(:id AS uuid) ORDER BY event_at DESC"), {"id": str(session_id)})).mappings().all()]
    return {"session_id": str(session_id), "detections": rows}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: uuid.UUID, _: Principal = Depends(require_role("SUPERADMIN")), db: AsyncSession = Depends(get_db)):
    enabled()
    await db.execute(text("UPDATE test_sessions SET status='closed', closed_at=NOW() WHERE id=CAST(:id AS uuid)"), {"id": str(session_id)})
    await db.commit()
    redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True).delete(f"test:{session_id}:detections")
    return {"status": "closed", "production_data_affected": False}
