"""Supervisor and per-feed runner for isolated Test Mode video streams."""
import argparse, base64, logging, os, signal, subprocess, sys, time
from datetime import datetime, timezone
import cv2, imageio_ffmpeg, psycopg2, redis

log=logging.getLogger("test_runner")
DB_URL=os.getenv("DATABASE_URL","")
REDIS_URL=os.getenv("REDIS_URL","redis://redis:6379")
FRAME_FPS=max(1,float(os.getenv("TEST_FRAME_FPS","3")))
RTSP_BASE=os.getenv("TEST_RTSP_BASE","rtsp://mediamtx:8554")
POLL_SECS=max(0.25,float(os.getenv("TEST_FEED_POLL_SECS","0.5")))
running=True

def stop(*_):
    global running
    running=False

def _publisher(source,session_id,stream_id,loop):
    return subprocess.Popen([
        imageio_ffmpeg.get_ffmpeg_exe(),"-hide_banner","-loglevel","error",
        "-re","-stream_loop","-1" if loop else "0","-i",source,
        "-map","0:v:0","-an","-c:v","libx264","-preset","ultrafast",
        "-tune","zerolatency","-g","30","-keyint_min","30","-sc_threshold","0",
        "-f","rtsp","-rtsp_transport","tcp",
        f"{RTSP_BASE}/test/{session_id}/cam{stream_id}"
    ],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def _start_feed(conn,session_id,row,feeds,publishers):
    stream_id,source,loop=row
    cap=cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to decode test video: {os.path.basename(source)}")
    width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); fps=cap.get(cv2.CAP_PROP_FPS)
    publisher=_publisher(source,session_id,int(stream_id),bool(loop))
    if publisher.poll() is not None:
        cap.release()
        raise RuntimeError(f"Unable to publish Test Feed {stream_id}")
    publishers[int(stream_id)]=publisher
    feeds[int(stream_id)]={"stream_id":int(stream_id),"source":source,"loop":bool(loop),"cap":cap,"next":0.0,"pts":0}
    with conn.cursor() as cur:
        cur.execute("UPDATE test_session_feeds SET width=%s,height=%s,fps=%s WHERE session_id=%s::uuid AND stream_id=%s",(width or None,height or None,fps or None,session_id,int(stream_id)))

def _stop_feed(stream_id,feeds,publishers):
    feed=feeds.pop(int(stream_id),None)
    if feed:
        try: feed["cap"].release()
        except Exception: pass
    proc=publishers.pop(int(stream_id),None)
    if proc:
        try: os.killpg(proc.pid,signal.SIGTERM)
        except (ProcessLookupError,PermissionError): pass

def _rows(conn,session_id):
    with conn.cursor() as cur:
        cur.execute("""SELECT f.stream_id,a.storage_key,f.loop
                       FROM test_session_feeds f
                       JOIN test_video_assets a ON a.id=f.asset_id
                       WHERE f.session_id=%s::uuid ORDER BY f.stream_id""",(session_id,))
        return cur.fetchall()

def runner(session_id):
    global running
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    conn=psycopg2.connect(DB_URL); conn.autocommit=True
    r=redis.from_url(REDIS_URL,decode_responses=True)
    feeds={}; publishers={}; frames=0; last_sync=0.0
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE test_sessions SET status='active',started_at=COALESCE(started_at,NOW()),error=NULL WHERE id=%s::uuid",(session_id,))
        while running:
            if r.get(f"test:stop:{session_id}"):
                break
            now=time.monotonic()
            for key in list(r.scan_iter(match=f"test:remove_feed:{session_id}:*")):
                try: stream_id=int(str(key).rsplit(":",1)[1])
                except (ValueError,IndexError): r.delete(key); continue
                _stop_feed(stream_id,feeds,publishers); r.delete(key)

            if now-last_sync>=POLL_SECS:
                rows=_rows(conn,session_id); desired={int(row[0]):row for row in rows}
                for stream_id in list(feeds):
                    if stream_id not in desired:
                        _stop_feed(stream_id,feeds,publishers)
                for stream_id,row in desired.items():
                    if stream_id not in feeds:
                        try: _start_feed(conn,session_id,row,feeds,publishers)
                        except Exception as exc:
                            log.error("Unable to start Test Feed %s: %s",stream_id,exc,exc_info=True)
                            with conn.cursor() as cur: cur.execute("UPDATE test_sessions SET error=%s WHERE id=%s::uuid",(str(exc)[:2000],session_id))
                last_sync=now

            for stream_id,feed in list(feeds.items()):
                if now<feed["next"]: continue
                publisher=publishers.get(stream_id)
                if not publisher or publisher.poll() is not None:
                    _stop_feed(stream_id,feeds,publishers)
                    try: _start_feed(conn,session_id,(stream_id,feed["source"],feed["loop"]),feeds,publishers)
                    except Exception: continue
                ok,frame=feed["cap"].read()
                if not ok:
                    if feed["loop"]:
                        feed["cap"].release(); cap=cv2.VideoCapture(feed["source"]); feed["cap"]=cap
                        if not cap.isOpened(): continue
                        ok,frame=cap.read()
                    if not ok: _stop_feed(stream_id,feeds,publishers); continue
                ok,encoded=cv2.imencode(".jpg",frame,[cv2.IMWRITE_JPEG_QUALITY,75])
                if not ok: continue
                timestamp=datetime.now(timezone.utc).isoformat()
                r.xadd("test:raw_frames",{
                    "schema_version":"1.0","session_id":session_id,
                    "cam_id":f"test:{session_id}:{stream_id}","stream_id":str(stream_id),
                    "source_ts":timestamp,"ingested_at":timestamp,"pts_ms":str(feed["pts"]),
                    "frame":base64.b64encode(encoded.tobytes()).decode()
                },maxlen=10000,approximate=True)
                feed["pts"]+=int(1000/FRAME_FPS); feed["next"]=now+1/FRAME_FPS; frames+=1

            if frames and frames%30==0:
                with conn.cursor() as cur: cur.execute("UPDATE test_sessions SET frames_processed=%s WHERE id=%s::uuid",(frames,session_id))
            time.sleep(0.01)

        for stream_id in list(feeds): _stop_feed(stream_id,feeds,publishers)
        with conn.cursor() as cur:
            cur.execute("UPDATE test_sessions SET frames_processed=%s,status=CASE WHEN status='active' THEN 'idle' ELSE status END WHERE id=%s::uuid",(frames,session_id))
    except Exception as exc:
        log.exception("Test runner failed")
        with conn.cursor() as cur: cur.execute("UPDATE test_sessions SET status='error',error=%s WHERE id=%s::uuid",(str(exc)[:2000],session_id))
    finally:
        for stream_id in list(feeds): _stop_feed(stream_id,feeds,publishers)
        try:r.close()
        except Exception:pass
        conn.close()

def supervise():
    while True:
        try:
            conn=psycopg2.connect(DB_URL); conn.autocommit=True
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM test_sessions WHERE status='starting' AND runner_pid IS NULL ORDER BY created_at LIMIT 1")
                row=cur.fetchone()
                if row:
                    sid=str(row[0]); proc=subprocess.Popen([sys.executable,"/app/test_runner.py","--session-id",sid],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    cur.execute("UPDATE test_sessions SET runner_pid=%s WHERE id=%s::uuid",(proc.pid,sid))
            conn.close()
        except Exception as exc:
            log.warning("Test supervisor: %s",exc)
        time.sleep(1)

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--session-id",required=True)
    runner(parser.parse_args().session_id)
