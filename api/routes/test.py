"""Video-backed test mode. It is deliberately isolated from operational data."""
import csv, io, mimetypes, os, signal, uuid
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from auth import ROLE_ORDER, Principal, current_principal, require_role
from database import get_db

router = APIRouter(prefix="/test", tags=["test"])
VIDEO_DIR, UPLOAD_DIR = Path(os.getenv("TEST_VIDEO_DIR", "/videos")), Path(os.getenv("TEST_UPLOAD_DIR", "/test_videos"))
MAX_UPLOAD_BYTES = int(os.getenv("TEST_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
ALLOWED_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}

def enabled():
    if os.getenv("TEST_ENDPOINT_ENABLED", "false").lower() != "true": raise HTTPException(404, "Video test mode is disabled")

async def require_test_video_viewer(
    principal: Principal = Depends(current_principal),
) -> Principal:
    """Authorize isolated test playback with the Sentinel session cookie."""
    if ROLE_ORDER.get(principal.role, 0) < ROLE_ORDER["VIEWER"]:
        raise HTTPException(403, "Insufficient role")
    return principal

def _probe(path: Path) -> dict:
    # The isolated ingestion subprocess is the single media decoder and fills
    # these observations before publishing frames.  The API only validates
    # safe local storage, keeping it lightweight and deterministic.
    return {"width": None, "height": None, "fps": None, "duration_seconds": None}

async def _register_asset(db: AsyncSession, path: Path, source_kind: str) -> dict:
    row = (await db.execute(text("""INSERT INTO test_video_assets(storage_key,display_name,source_kind,width,height,fps,duration_seconds,size_bytes)
      VALUES(:key,:name,:kind,:width,:height,:fps,:duration_seconds,:size)
      ON CONFLICT(storage_key) DO UPDATE SET display_name=EXCLUDED.display_name,width=EXCLUDED.width,height=EXCLUDED.height,fps=EXCLUDED.fps,duration_seconds=EXCLUDED.duration_seconds,size_bytes=EXCLUDED.size_bytes
      RETURNING id,display_name,source_kind,width,height,fps,duration_seconds,size_bytes"""), {"key": str(path), "name": path.name, "kind": source_kind, "size": path.stat().st_size, **_probe(path)})).mappings().one()
    return dict(row)

async def _close_orphaned_sessions(db: AsyncSession) -> None:
    """Release interrupted test-only sessions that never received a feed/runner."""
    await db.execute(text("""UPDATE test_sessions s SET status='closed', closed_at=COALESCE(closed_at,NOW()),
      error=COALESCE(error,'Test session was interrupted before startup')
      WHERE s.status IN ('starting','active') AND s.runner_pid IS NULL
      AND NOT EXISTS (SELECT 1 FROM test_session_feeds f WHERE f.session_id=s.id)"""))

class TestFeed(BaseModel):
    asset_id: uuid.UUID
    camera_label: str = Field(default="", max_length=255)
    loop: bool = True

class TestSessionCreate(BaseModel):
    name: str = Field(default="Video test session", min_length=1, max_length=255)
    cameras: list[TestFeed] = Field(min_length=1, max_length=8)

@router.get("/assets")
async def list_assets(_: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    enabled(); VIDEO_DIR.mkdir(parents=True, exist_ok=True); UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for root, kind in ((VIDEO_DIR, "bundled"), (UPLOAD_DIR, "upload")):
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES:
                try: await _register_asset(db, path, kind)
                except HTTPException: continue
    await db.commit(); rows = await db.execute(text("SELECT a.id,a.display_name,a.source_kind,a.width,a.height,a.fps,a.duration_seconds,a.size_bytes, EXISTS(SELECT 1 FROM test_session_feeds f WHERE f.asset_id=a.id) AS in_use FROM test_video_assets a ORDER BY a.source_kind,a.display_name"))
    return [dict(row) for row in rows.mappings().all()]

@router.post("/feeds/upload", status_code=201)
async def upload_feed(file: UploadFile = File(...), _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    enabled(); suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES: raise HTTPException(415, "Supported video formats: MP4, MKV, MOV, WebM, AVI, M4V")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True); target = UPLOAD_DIR / f"{uuid.uuid4()}{suffix}"; written = 0
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES: raise HTTPException(413, "Video exceeds the configured test-upload limit")
                output.write(chunk)
        asset = await _register_asset(db, target, "upload"); await db.commit(); return asset
    except Exception:
        target.unlink(missing_ok=True); raise

@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: uuid.UUID,
    _: Principal = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    enabled()
    row = (await db.execute(text("""
        SELECT id, storage_key, display_name
        FROM test_video_assets
        WHERE id=CAST(:id AS uuid)
        FOR UPDATE
    """), {"id": str(asset_id)})).mappings().first()
    if not row:
        raise HTTPException(404, "Test video not found")

    refs = (await db.execute(text("""
        SELECT f.session_id, f.stream_id
        FROM test_session_feeds f
        JOIN test_sessions s ON s.id=f.session_id
        WHERE f.asset_id=CAST(:id AS uuid)
          AND s.status IN ('starting','active')
    """), {"id": str(asset_id)})).mappings().all()

    import redis
    client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    for ref in refs:
        client.setex(f"test:remove_feed:{ref['session_id']}:{ref['stream_id']}", 60, "1")

    await db.execute(
        text("DELETE FROM test_session_feeds WHERE asset_id=CAST(:id AS uuid)"),
        {"id": str(asset_id)},
    )
    await db.execute(
        text("DELETE FROM test_video_assets WHERE id=CAST(:id AS uuid)"),
        {"id": str(asset_id)},
    )
    await db.commit()

    path = Path(row["storage_key"])
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(500, "Test video metadata was removed but the video file could not be deleted") from exc

    return {"status": "removed", "id": str(asset_id), "display_name": row["display_name"]}


@router.delete("/sessions/{session_id}/feeds/{stream_id}")
async def delete_session_feed(
    session_id: uuid.UUID,
    stream_id: int,
    _: Principal = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    enabled()
    row = (await db.execute(text("""
        SELECT id
        FROM test_session_feeds
        WHERE session_id=CAST(:session AS uuid) AND stream_id=:stream
        FOR UPDATE
    """), {"session": str(session_id), "stream": stream_id})).mappings().first()
    if not row:
        raise HTTPException(404, "Test feed not found")

    import redis
    client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    client.setex(f"test:remove_feed:{session_id}:{stream_id}", 60, "1")
    await db.execute(
        text("DELETE FROM test_session_feeds WHERE session_id=CAST(:session AS uuid) AND stream_id=:stream"),
        {"session": str(session_id), "stream": stream_id},
    )
    await db.commit()
    return {"status": "removed", "session_id": str(session_id), "stream_id": stream_id}


@router.post("/sessions", status_code=201)
async def create_session(body: TestSessionCreate, principal: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    enabled()
    await _close_orphaned_sessions(db)
    if await db.scalar(text("SELECT 1 FROM test_sessions WHERE status IN ('starting','active') LIMIT 1")): raise HTTPException(409, "Only one isolated video test session may run at a time")
    assets = {}
    for feed in body.cameras:
        row = (await db.execute(text("SELECT * FROM test_video_assets WHERE id=CAST(:id AS uuid)"), {"id": str(feed.asset_id)})).mappings().first()
        if not row or not Path(row["storage_key"]).is_file(): raise HTTPException(422, "A selected test video is unavailable")
        assets[feed.asset_id] = dict(row)
    session = (await db.execute(text("INSERT INTO test_sessions(name,created_by,status,loop,started_at) VALUES(:name,:actor,'starting',TRUE,NOW()) RETURNING id,name,status,created_at"), {"name": body.name, "actor": principal.username})).mappings().one(); session_id = str(session["id"])
    for number, feed in enumerate(body.cameras, start=1):
        asset = assets[feed.asset_id]; label = feed.camera_label.strip() or f"Test Camera {number} — {asset['display_name']}"
        await db.execute(text("""INSERT INTO test_session_feeds(session_id,asset_id,stream_id,camera_label,rtsp_path,hls_path,loop,width,height,fps)
          VALUES(CAST(:session AS uuid),CAST(:asset AS uuid),:stream,:label,:rtsp,:hls,:loop,:width,:height,:fps)"""), {"session": session_id,"asset": str(feed.asset_id),"stream": number,"label": label,"rtsp": f"rtsp://mediamtx:8554/test/{session_id}/cam{number}","hls": f"/test-hls/test/{session_id}/cam{number}/index.m3u8","loop": feed.loop,"width": asset["width"],"height": asset["height"],"fps": asset["fps"]})
    # The existing ingestion service detects this starting row and spawns one
    # isolated decoder subprocess. No operational worker or Docker service is
    # restarted to run a test.
    await db.commit(); return {**dict(session), "id": session_id, "runner_pid": None, "production_data_affected": False}

@router.get("/sessions/active")
async def active_session(_: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    enabled(); await _close_orphaned_sessions(db); await db.commit()
    row = (await db.execute(text("SELECT id,name,status,created_at FROM test_sessions WHERE status IN ('starting','active') ORDER BY created_at DESC LIMIT 1"))).mappings().first()
    return {**dict(row), "id": str(row["id"])} if row else None

@router.get("/sessions/{session_id}/status")
async def session_status(session_id: uuid.UUID, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    enabled(); row = (await db.execute(text("""SELECT s.id,s.name,s.status,s.created_at,s.started_at,s.closed_at,s.frames_processed,s.error,(SELECT COUNT(*) FROM test_detections d WHERE d.session_id=s.id) detections,(SELECT COUNT(*) FROM test_alerts a WHERE a.session_id=s.id) alerts FROM test_sessions s WHERE s.id=CAST(:id AS uuid)"""), {"id": str(session_id)})).mappings().first()
    if not row: raise HTTPException(404, "Test session not found")
    return dict(row)

@router.get("/sessions/{session_id}/cameras")
async def session_cameras(session_id: uuid.UUID, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    enabled(); rows = (await db.execute(text("SELECT f.id,f.stream_id,f.camera_label,f.hls_path,f.width,f.height,f.fps,s.status FROM test_session_feeds f JOIN test_sessions s ON s.id=f.session_id WHERE f.session_id=CAST(:id AS uuid) ORDER BY f.stream_id"), {"id": str(session_id)})).mappings().all()
    if not rows: raise HTTPException(404, "Test session not found")
    return [{"id": f"test-{row['id']}","stream_id": row["stream_id"],"name": row["camera_label"],"location": "Isolated video test","hls_url": row["hls_path"],"whep_url": "","stream_url": f"/api/test/sessions/{session_id}/feeds/{row['stream_id']}/video","codec": "H.264 (MediaMTX)","width": row["width"],"height": row["height"],"fps": row["fps"],"effective_codec": "H.264 (MediaMTX)","effective_width": row["width"],"effective_height": row["height"],"effective_fps": row["fps"],"status": row["status"],"health_status": row["status"],"connectivity_status": row["status"],"is_test": True} for row in rows]

@router.get("/sessions/{session_id}/feeds/{stream_id}/video")
async def session_video(session_id: uuid.UUID, stream_id: int, _: Principal = Depends(require_test_video_viewer), db: AsyncSession = Depends(get_db)):
    """Browser fallback for a random, test-only session path while HLS warms.

    Browser playback is viewer-authorized; test uploads are never public.
    """
    enabled(); row = (await db.execute(text("SELECT a.storage_key FROM test_session_feeds f JOIN test_video_assets a ON a.id=f.asset_id WHERE f.session_id=CAST(:id AS uuid) AND f.stream_id=:stream"), {"id": str(session_id),"stream": stream_id})).mappings().first()
    if not row or not Path(row["storage_key"]).is_file(): raise HTTPException(404, "Test video not found")
    path = Path(row["storage_key"])
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream", filename=path.name)

@router.get("/sessions/{session_id}/results")
async def session_results(session_id: uuid.UUID, plate: str | None = Query(None, max_length=100), cam_id: str | None = Query(None, max_length=64), from_dt: datetime | None = Query(None), to_dt: datetime | None = Query(None), detection_type: str | None = Query(None, max_length=64), limit: int = Query(100, ge=1, le=500), format: str = Query("json", pattern="^(json|csv)$"), _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    enabled()
    stream_id = None
    if cam_id:
        value = cam_id.removeprefix("test-")
        if value.isdigit(): stream_id = int(value)
        else:
            try: feed_id = str(uuid.UUID(value))
            except ValueError as exc: raise HTTPException(422, "cam_id must be a test camera id or stream id") from exc
            stream_id = await db.scalar(text("SELECT stream_id FROM test_session_feeds WHERE session_id=CAST(:session AS uuid) AND id=CAST(:feed AS uuid)"), {"session": str(session_id), "feed": feed_id})
            if stream_id is None: raise HTTPException(404, "Test camera not found in this session")
    conditions, params = ["td.session_id=CAST(:session AS uuid)"], {"session": str(session_id), "limit": limit}
    if plate: conditions.append("COALESCE(td.plate_text, '') ILIKE :plate"); params["plate"] = f"%{plate}%"
    if stream_id is not None: conditions.append("td.stream_id=:stream_id"); params["stream_id"] = stream_id
    if from_dt: conditions.append("td.event_at >= :from_dt"); params["from_dt"] = from_dt
    if to_dt: conditions.append("td.event_at <= :to_dt"); params["to_dt"] = to_dt
    if detection_type: conditions.append("td.detection_type=:detection_type"); params["detection_type"] = detection_type
    detections = [dict(row) for row in (await db.execute(text(f"""SELECT td.*, COALESCE(f.camera_label, td.camera_label) AS cam_name
        FROM test_detections td LEFT JOIN test_session_feeds f ON f.session_id=td.session_id AND f.stream_id=td.stream_id
        WHERE {' AND '.join(conditions)} ORDER BY td.event_at DESC LIMIT :limit"""), params)).mappings().all()]
    if format == "csv":
        fields = ["id", "event_at", "stream_id", "cam_name", "detection_type", "plate_text", "confidence", "track_id"]
        buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(detections)
        return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=test-{session_id}-results.csv"})
    alerts = [dict(row) for row in (await db.execute(text("SELECT * FROM test_alerts WHERE session_id=CAST(:id AS uuid) ORDER BY event_at DESC LIMIT 500"), {"id": str(session_id)})).mappings().all()]
    tracks = [dict(row) for row in (await db.execute(text("SELECT * FROM test_tracks WHERE session_id=CAST(:id AS uuid) ORDER BY last_seen_at DESC LIMIT 500"), {"id": str(session_id)})).mappings().all()]
    return {"session_id": str(session_id), "detections": detections, "alerts": alerts, "tracks": tracks, "production_data_affected": False}

@router.get("/sessions/{session_id}/results/export")
async def export_results(session_id: uuid.UUID, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    enabled(); rows = (await db.execute(text("SELECT camera_label,detection_type,plate_text,confidence,event_at,track_id FROM test_detections WHERE session_id=CAST(:id AS uuid) ORDER BY event_at DESC"), {"id": str(session_id)})).mappings().all(); buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=["camera_label","detection_type","plate_text","confidence","event_at","track_id"]); writer.writeheader(); writer.writerows(rows)
    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=test-{session_id}-results.csv"})

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: uuid.UUID, _: Principal = Depends(require_role("ADMIN")), db: AsyncSession = Depends(get_db)):
    enabled(); row = (await db.execute(text("SELECT runner_pid FROM test_sessions WHERE id=CAST(:id AS uuid)"), {"id": str(session_id)})).mappings().first()
    if not row: raise HTTPException(404, "Test session not found")
    if row["runner_pid"]:
        try: os.killpg(int(row["runner_pid"]), signal.SIGTERM)
        except (ProcessLookupError, PermissionError): pass
    import redis
    client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    client.setex(f"test:stop:{session_id}", 60, "1")
    client.delete("test:raw_frames", "test:detections", "test:alerts", "test:cam_resets")
    await db.execute(text("DELETE FROM test_sessions WHERE id=CAST(:id AS uuid)"), {"id": str(session_id)}); await db.commit()
    return {"status": "cleared", "production_data_affected": False}
