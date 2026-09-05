"""Incremental live-feed management for isolated Test Mode sessions."""
from __future__ import annotations

import os
import signal
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import Principal, require_role
from database import get_db

router = APIRouter(prefix="/test", tags=["test-feeds"])


class TestFeedRequest(BaseModel):
    asset_id: uuid.UUID
    camera_label: str = Field(default="", max_length=255)
    loop: bool = True


def _enabled() -> None:
    if os.getenv("TEST_ENDPOINT_ENABLED", "false").lower() != "true":
        raise HTTPException(404, "Video test mode is disabled")


async def _close_empty_session(session_id: uuid.UUID, db: AsyncSession) -> bool:
    remaining = await db.scalar(
        text("SELECT COUNT(*) FROM test_session_feeds WHERE session_id=CAST(:id AS uuid)"),
        {"id": str(session_id)},
    )
    if int(remaining or 0):
        return False
    row = (
        await db.execute(
            text("SELECT runner_pid FROM test_sessions WHERE id=CAST(:id AS uuid) AND status IN ('starting','active') FOR UPDATE"),
            {"id": str(session_id)},
        )
    ).mappings().first()
    if not row:
        return False
    if row["runner_pid"]:
        try:
            os.killpg(int(row["runner_pid"]), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    import redis
    client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    try:
        client.setex(f"test:stop:{session_id}", 60, "1")
    finally:
        client.close()
    await db.execute(
        text("UPDATE test_sessions SET status='closed',closed_at=COALESCE(closed_at,NOW()),runner_pid=NULL,error=COALESCE(error,'Test session closed after its final feed was removed') WHERE id=CAST(:id AS uuid)"),
        {"id": str(session_id)},
    )
    return True


@router.post("/sessions/{session_id}/feeds", status_code=201)
async def add_session_feed(
    session_id: uuid.UUID,
    feed: TestFeedRequest,
    _: Principal = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    session = (
        await db.execute(
            text("SELECT id,status FROM test_sessions WHERE id=CAST(:id AS uuid) FOR UPDATE"),
            {"id": str(session_id)},
        )
    ).mappings().first()
    if not session:
        raise HTTPException(404, "Test session not found")
    if session["status"] not in ("starting", "active"):
        raise HTTPException(409, "Test session is not active")
    asset = (
        await db.execute(
            text("SELECT * FROM test_video_assets WHERE id=CAST(:id AS uuid)"),
            {"id": str(feed.asset_id)},
        )
    ).mappings().first()
    if not asset or not Path(asset["storage_key"]).is_file():
        raise HTTPException(422, "Selected test video is unavailable")
    duplicate = await db.scalar(
        text("SELECT 1 FROM test_session_feeds WHERE session_id=CAST(:session AS uuid) AND asset_id=CAST(:asset AS uuid)"),
        {"session": str(session_id), "asset": str(feed.asset_id)},
    )
    if duplicate:
        raise HTTPException(409, "This video is already in the live Test Feed")
    count = await db.scalar(
        text("SELECT COUNT(*) FROM test_session_feeds WHERE session_id=CAST(:session AS uuid)"),
        {"session": str(session_id)},
    )
    if int(count or 0) >= 8:
        raise HTTPException(409, "A Test Mode session can contain at most 8 live feeds")
    stream_id = int(await db.scalar(
        text("SELECT COALESCE(MAX(stream_id),0)+1 FROM test_session_feeds WHERE session_id=CAST(:session AS uuid)"),
        {"session": str(session_id)},
    ) or 1)
    label = feed.camera_label.strip() or f"Test Camera {stream_id} — {asset['display_name']}"
    row = (
        await db.execute(
            text("""INSERT INTO test_session_feeds(session_id,asset_id,stream_id,camera_label,rtsp_path,hls_path,loop,width,height,fps)
            VALUES(CAST(:session AS uuid),CAST(:asset AS uuid),:stream,:label,:rtsp,:hls,:loop,:width,:height,:fps)
            RETURNING id,stream_id,camera_label,hls_path,width,height,fps"""),
            {
                "session": str(session_id), "asset": str(feed.asset_id), "stream": stream_id,
                "label": label, "rtsp": f"rtsp://mediamtx:8554/test/{session_id}/cam{stream_id}",
                "hls": f"/test-hls/test/{session_id}/cam{stream_id}/index.m3u8", "loop": feed.loop,
                "width": asset["width"], "height": asset["height"], "fps": asset["fps"],
            },
        )
    ).mappings().one()
    await db.commit()
    return {"id": str(row["id"]), "stream_id": row["stream_id"], "name": row["camera_label"], "hls_url": row["hls_path"], "is_test": True, "status": session["status"], "production_data_affected": False}


@router.delete("/sessions/{session_id}/feeds/{stream_id}")
async def delete_session_feed(
    session_id: uuid.UUID,
    stream_id: int,
    _: Principal = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    row = (
        await db.execute(
            text("SELECT id FROM test_session_feeds WHERE session_id=CAST(:session AS uuid) AND stream_id=:stream FOR UPDATE"),
            {"session": str(session_id), "stream": stream_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Test feed not found")
    import redis
    client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    try:
        client.setex(f"test:remove_feed:{session_id}:{stream_id}", 60, "1")
    finally:
        client.close()
    await db.execute(
        text("DELETE FROM test_session_feeds WHERE session_id=CAST(:session AS uuid) AND stream_id=:stream"),
        {"session": str(session_id), "stream": stream_id},
    )
    session_closed = await _close_empty_session(session_id, db)
    await db.commit()
    return {"status": "session_closed" if session_closed else "removed", "session_id": str(session_id), "stream_id": stream_id}


@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: uuid.UUID,
    _: Principal = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    row = (
        await db.execute(
            text("SELECT id,storage_key,display_name FROM test_video_assets WHERE id=CAST(:id AS uuid) FOR UPDATE"),
            {"id": str(asset_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Test video not found")
    path = Path(row["storage_key"])
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(409, f"Test video cannot be permanently removed: {exc}") from exc
    refs = (
        await db.execute(
            text("SELECT f.session_id,f.stream_id FROM test_session_feeds f JOIN test_sessions s ON s.id=f.session_id WHERE f.asset_id=CAST(:id AS uuid) AND s.status IN ('starting','active')"),
            {"id": str(asset_id)},
        )
    ).mappings().all()
    import redis
    client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    try:
        for ref in refs:
            client.setex(f"test:remove_feed:{ref['session_id']}:{ref['stream_id']}", 60, "1")
    finally:
        client.close()
    await db.execute(text("DELETE FROM test_session_feeds WHERE asset_id=CAST(:id AS uuid)"), {"id": str(asset_id)})
    for ref in refs:
        await _close_empty_session(ref["session_id"], db)
    await db.execute(text("DELETE FROM test_video_assets WHERE id=CAST(:id AS uuid)"), {"id": str(asset_id)})
    await db.commit()
    return {"status": "removed", "id": str(asset_id), "display_name": row["display_name"], "production_data_affected": False}
