"""Supervisor and subprocess for the isolated video-test raw-frame stream."""
import argparse, base64, os, signal, subprocess, sys, time
from datetime import datetime, timezone
import cv2, imageio_ffmpeg, psycopg2, redis

DB_URL, REDIS_URL = os.getenv("DATABASE_URL", ""), os.getenv("REDIS_URL", "redis://localhost:6379")
FRAME_FPS = max(1, float(os.getenv("TEST_FRAME_FPS", "3"))); RTSP_BASE = os.getenv("TEST_RTSP_BASE", "rtsp://mediamtx:8554"); running = True
def stop(*_):
    global running; running = False

def _start_feed(session_id, row, conn, publishers, feeds):
    stream_id, source, loop = int(row[0]), row[1], bool(row[2])
    if stream_id in feeds:
        return
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot decode test source: {os.path.basename(source)}")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE test_session_feeds SET width=%s,height=%s,fps=%s WHERE session_id=%s::uuid AND stream_id=%s",
            (width or None, height or None, source_fps or None, session_id, stream_id),
        )
    publishers[stream_id] = subprocess.Popen(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
            "-re", "-stream_loop", "-1" if loop else "0", "-i", source,
            "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-tune", "zerolatency", "-g", "30", "-keyint_min", "30",
            "-sc_threshold", "0", "-f", "rtsp", "-rtsp_transport", "tcp",
            f"{RTSP_BASE}/test/{session_id}/cam{stream_id}",
        ],
        start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    feeds[stream_id] = {"stream_id": stream_id, "cap": cap, "loop": loop, "next": 0.0, "pts": 0}


def _stop_feed(stream_id, publishers, feeds):
    feed = feeds.pop(stream_id, None)
    if feed is not None:
        feed["cap"].release()
    process = publishers.pop(stream_id, None)
    if process is not None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
def runner(session_id: str):
    global running
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    client = redis.from_url(REDIS_URL, decode_responses=True)
    feeds, publishers = {}, {}
    completed_streams, failed_streams = set(), set()
    frames, last_db_poll = 0, 0.0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT f.stream_id,a.storage_key,f.loop FROM test_session_feeds f JOIN test_video_assets a ON a.id=f.asset_id WHERE f.session_id=%s::uuid ORDER BY f.stream_id",
                (session_id,),
            )
            initial_rows = cur.fetchall()
            cur.execute(
                "UPDATE test_sessions SET status='active',started_at=COALESCE(started_at,NOW()),error=NULL WHERE id=%s::uuid",
                (session_id,),
            )
        for row in initial_rows:
            try:
                _start_feed(session_id, row, conn, publishers, feeds)
            except Exception as exc:
                failed_streams.add(int(row[0]))
                with conn.cursor() as cur:
                    cur.execute("UPDATE test_sessions SET error=%s WHERE id=%s::uuid", (str(exc)[:2000], session_id))

        while running:
            if client.get(f"test:stop:{session_id}"):
                break

            now = time.monotonic()
            if now - last_db_poll >= 1.0:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT f.stream_id,a.storage_key,f.loop FROM test_session_feeds f JOIN test_video_assets a ON a.id=f.asset_id WHERE f.session_id=%s::uuid ORDER BY f.stream_id",
                        (session_id,),
                    )
                    rows = cur.fetchall()
                desired = {int(row[0]) for row in rows}

                for row in rows:
                    stream_id = int(row[0])
                    if stream_id in feeds or stream_id in completed_streams or stream_id in failed_streams:
                        continue
                    try:
                        _start_feed(session_id, row, conn, publishers, feeds)
                        failed_streams.discard(stream_id)
                    except Exception as exc:
                        failed_streams.add(stream_id)
                        with conn.cursor() as cur:
                            cur.execute("UPDATE test_sessions SET error=%s WHERE id=%s::uuid", (str(exc)[:2000], session_id))

                for stream_id in list(feeds):
                    if stream_id not in desired:
                        _stop_feed(stream_id, publishers, feeds)
                        completed_streams.discard(stream_id)

                if feeds:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE test_sessions SET status='active' WHERE id=%s::uuid", (session_id,))
                elif not rows:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE test_sessions SET status='idle',frames_processed=%s WHERE id=%s::uuid", (frames, session_id))
                last_db_poll = now

            for key in list(client.scan_iter(match=f"test:remove_feed:{session_id}:*")):
                try:
                    removed_stream = int(str(key).rsplit(":", 1)[1])
                except (ValueError, IndexError):
                    client.delete(key)
                    continue
                _stop_feed(removed_stream, publishers, feeds)
                client.delete(key)
                with conn.cursor() as cur:
                    cur.execute("UPDATE test_sessions SET frames_processed=%s WHERE id=%s::uuid", (frames, session_id))

            for stream_id, feed in list(feeds.items()):
                if now < feed["next"]:
                    continue
                ok, frame = feed["cap"].read()
                if not ok:
                    if feed["loop"]:
                        feed["cap"].set(cv2.CAP_PROP_POS_FRAMES, 0)
                        feed["next"] = now + 0.02
                        continue
                    _stop_feed(stream_id, publishers, feeds)
                    completed_streams.add(stream_id)
                    continue
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if not ok:
                    continue
                timestamp = datetime.now(timezone.utc).isoformat()
                client.xadd(
                    "test:raw_frames",
                    {
                        "schema_version": "1.0",
                        "session_id": session_id,
                        "cam_id": f"test:{session_id}:{stream_id}",
                        "stream_id": str(stream_id),
                        "source_ts": timestamp,
                        "ingested_at": timestamp,
                        "pts_ms": str(feed["pts"]),
                        "frame": base64.b64encode(encoded.tobytes()).decode(),
                    },
                    maxlen=10000,
                    approximate=True,
                )
                feed["pts"] += int(1000 / FRAME_FPS)
                feed["next"] = now + 1 / FRAME_FPS
                frames += 1

            time.sleep(0.004)

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE test_sessions SET frames_processed=%s,status=CASE WHEN status IN ('active','idle') THEN 'closed' ELSE status END,closed_at=CASE WHEN status IN ('active','idle') THEN NOW() ELSE closed_at END WHERE id=%s::uuid",
                (frames, session_id),
            )
    except Exception as exc:
        with conn.cursor() as cur:
            cur.execute("UPDATE test_sessions SET status='error',error=%s WHERE id=%s::uuid", (str(exc)[:2000], session_id))
    finally:
        for stream_id in list(feeds):
            _stop_feed(stream_id, publishers, feeds)
        try:
            client.close()
        except Exception:
            pass
        conn.close()

def supervise():
    """One active session limit makes process ownership and stream cleanup unambiguous."""
    last_catalogue_refresh = 0.0
    while True:
        try:
            conn = psycopg2.connect(DB_URL); conn.autocommit = True
            with conn.cursor() as cur:
                if time.monotonic() - last_catalogue_refresh > 15:
                    cur.execute("SELECT id,storage_key FROM test_video_assets WHERE width IS NULL OR height IS NULL OR fps IS NULL")
                    for asset_id, source in cur.fetchall():
                        cap = cv2.VideoCapture(source)
                        if cap.isOpened():
                            width, height, fps, frames = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
                            cur.execute("UPDATE test_video_assets SET width=%s,height=%s,fps=%s,duration_seconds=%s WHERE id=%s::uuid", (width or None,height or None,fps or None,(frames / fps) if fps and frames else None,str(asset_id)))
                        cap.release()
                    last_catalogue_refresh = time.monotonic()
                cur.execute("SELECT id FROM test_sessions WHERE status='starting' AND runner_pid IS NULL ORDER BY created_at LIMIT 1"); row = cur.fetchone()
                if row:
                    session_id = str(row[0]); process = subprocess.Popen([sys.executable,"/app/test_runner.py","--session-id",session_id],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    cur.execute("UPDATE test_sessions SET runner_pid=%s WHERE id=%s::uuid",(process.pid,session_id))
            conn.close()
        except Exception: pass
        time.sleep(2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--session-id",required=True); runner(parser.parse_args().session_id)
