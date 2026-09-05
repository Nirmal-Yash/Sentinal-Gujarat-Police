"""Supervisor and subprocess for the isolated video-test raw-frame stream."""
import argparse, base64, os, signal, subprocess, sys, time
from datetime import datetime, timezone
import cv2, imageio_ffmpeg, psycopg2, redis

DB_URL, REDIS_URL = os.getenv("DATABASE_URL", ""), os.getenv("REDIS_URL", "redis://localhost:6379")
FRAME_FPS = max(1, float(os.getenv("TEST_FRAME_FPS", "3"))); RTSP_BASE = os.getenv("TEST_RTSP_BASE", "rtsp://mediamtx:8554"); running = True
def stop(*_):
    global running; running = False

def runner(session_id: str):
    global running
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    conn = psycopg2.connect(DB_URL); conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("""SELECT f.stream_id,a.storage_key,f.loop FROM test_session_feeds f JOIN test_video_assets a ON a.id=f.asset_id WHERE f.session_id=%s::uuid ORDER BY f.stream_id""", (session_id,)); rows = cur.fetchall()
        cur.execute("UPDATE test_sessions SET status='active',started_at=COALESCE(started_at,NOW()),error=NULL WHERE id=%s::uuid", (session_id,))
    feeds, publishers, frames = [], {}, 0
    try:
        for stream_id, source, loop in rows:
            cap = cv2.VideoCapture(source)
            if not cap.isOpened(): raise RuntimeError(f"Cannot decode test source: {os.path.basename(source)}")
            width, height, source_fps = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), cap.get(cv2.CAP_PROP_FPS)
            with conn.cursor() as cur: cur.execute("UPDATE test_session_feeds SET width=%s,height=%s,fps=%s WHERE session_id=%s::uuid AND stream_id=%s", (width or None,height or None,source_fps or None,session_id,stream_id))
            publishers[stream_id] = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),"-hide_banner","-loglevel","error","-re","-stream_loop","-1" if loop else "0","-i",source,"-map","0:v:0","-an","-c:v","libx264","-preset","ultrafast","-tune","zerolatency","-g","30","-keyint_min","30","-sc_threshold","0","-f","rtsp","-rtsp_transport","tcp",f"{RTSP_BASE}/test/{session_id}/cam{stream_id}"], start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            feeds.append({"stream_id": stream_id,"cap": cap,"loop": loop,"next": 0.0,"pts": 0})
        client = redis.from_url(REDIS_URL, decode_responses=False)
        while running and feeds:
            if client.get(f"test:stop:{session_id}"):
                break
            now = time.monotonic()
            for key in list(client.scan_iter(match=f'test:remove_feed:{session_id}:*')):
                try: removed_stream = int(str(key).rsplit(':',1)[1])
                except (ValueError, IndexError): client.delete(key); continue
                for feed in list(feeds):
                    if int(feed['stream_id']) != removed_stream: continue
                    feed['cap'].release()
                    feeds.remove(feed)
                    process = publishers.pop(removed_stream, None)
                    if process is not None:
                        try: os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError: pass
                client.delete(key)
                with conn.cursor() as cur:
                    cur.execute("UPDATE test_sessions SET frames_processed=%s WHERE id=%s::uuid", (frames,session_id))
            if not feeds:
                break
            for feed in list(feeds):
                if now < feed["next"]: continue
                ok, frame = feed["cap"].read()
                if not ok:
                    if feed["loop"]: feed["cap"].set(cv2.CAP_PROP_POS_FRAMES, 0); continue
                    feed["cap"].release(); feeds.remove(feed); continue
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if not ok: continue
                timestamp = datetime.now(timezone.utc).isoformat()
                client.xadd("test:raw_frames", {b"schema_version": b"1.0",b"session_id": session_id.encode(),b"cam_id": f"test:{session_id}:{feed['stream_id']}".encode(),b"stream_id": str(feed["stream_id"]).encode(),b"source_ts": timestamp.encode(),b"ingested_at": timestamp.encode(),b"pts_ms": str(feed["pts"]).encode(),b"frame": base64.b64encode(encoded.tobytes())}, maxlen=10000, approximate=True)
                feed["pts"] += int(1000 / FRAME_FPS); feed["next"] = now + 1 / FRAME_FPS; frames += 1
            if frames and frames % 30 == 0:
                with conn.cursor() as cur: cur.execute("UPDATE test_sessions SET frames_processed=%s WHERE id=%s::uuid", (frames,session_id))
            time.sleep(.004)
        with conn.cursor() as cur: cur.execute("UPDATE test_sessions SET frames_processed=%s,status=CASE WHEN status='active' THEN 'idle' ELSE status END WHERE id=%s::uuid", (frames,session_id))
    except Exception as exc:
        with conn.cursor() as cur: cur.execute("UPDATE test_sessions SET status='error',error=%s WHERE id=%s::uuid", (str(exc)[:2000],session_id))
    finally:
        for feed in feeds: feed["cap"].release()
        for process in publishers.values():
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
        conn.close()

def supervise():
    """One active session limit makes process ownership and stream cleanup unambiguous."""
    last_catalogue_refresh = 0.0
    while True:
        try:
            conn = psycopg2.connect(DB_URL); conn.autocommit = True
            with conn.cursor() as cur:
                # Source metadata is observed by the same OpenCV decoder that
                # processes the test feed. It is kept solely in test assets.
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
