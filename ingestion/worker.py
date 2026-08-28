#!/usr/bin/env python3
"""Ingestion Worker — live RTSP ingestion with adaptive operational telemetry."""
import os, sys, time, base64, logging, uuid, threading
from datetime import datetime, timezone
from multiprocessing import Process

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import cv2
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from stream_adapters import adapter_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s [INGEST][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DB_URL = os.getenv("DATABASE_URL", "")
FRAME_FPS = max(0.5, float(os.getenv("FRAME_FPS", "3")))
JPEG_Q = int(os.getenv("JPEG_QUALITY", "70"))
MAX_CAMS = max(1, int(os.getenv("MAX_CONCURRENT_CAMERAS", "50")))
CATALOGUE_SYNC_INTERVAL = max(30, int(os.getenv("CATALOGUE_SYNC_INTERVAL", "300")))
RECONNECT_MAX_DELAY = max(5, int(os.getenv("RECONNECT_MAX_DELAY", "30")))
STREAM_KEY = "raw_frames"; STREAM_MAX = 3000
ENCODE_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q]


def get_cameras():
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id,name,stream_id,rtsp_url,codec FROM cameras WHERE status='active' AND rtsp_url IS NOT NULL AND rtsp_url<>'' ORDER BY stream_id LIMIT %s", (MAX_CAMS,))
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def set_status(cam_id, status):
    health = {"active": "healthy", "reconnecting": "reconnecting", "offline": "offline"}.get(status, "unknown")
    connectivity = {"active": "connected", "reconnecting": "reconnecting", "offline": "disconnected"}.get(status, "unknown")
    try:
        with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
            cur.execute("UPDATE cameras SET connectivity_status=%s,health_status=%s,last_seen_at=CASE WHEN %s='active' THEN NOW() ELSE last_seen_at END,updated_at=NOW() WHERE id=%s", (connectivity, health, status, str(cam_id)))
    except Exception as exc:
        log.warning("Status update failed: %s", exc)


def update_runtime_observation(cam_id, width, height, source_fps, decode_fps, published_fps, codec, status="active"):
    """Persist distinct observed rates and an honest historical health observation."""
    health = {"active": "healthy", "reconnecting": "reconnecting", "offline": "offline"}.get(status, "unknown")
    connectivity = {"active": "connected", "reconnecting": "reconnecting", "offline": "disconnected"}.get(status, "unknown")
    try:
        with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
            cur.execute("""UPDATE cameras SET observed_width=%s,observed_height=%s,
                observed_fps=%s,observed_source_fps=%s,observed_decode_fps=%s,
                observed_published_fps=%s,observed_codec=%s,observed_at=NOW(),
                last_frame_at=NOW(),last_seen_at=NOW(),
                health_status=%s,connectivity_status=%s,updated_at=NOW() WHERE id=%s""",
                (width, height, source_fps, decode_fps, published_fps, codec, health, connectivity, str(cam_id)))
            cur.execute("""INSERT INTO camera_health_observations
                (camera_id,health_status,source_fps,decode_fps,published_fps,reconnect_count,decode_failure_count)
                SELECT id,%s,%s,%s,%s,reconnect_count,decode_failure_count FROM cameras WHERE id=%s""",
                (health, source_fps, decode_fps, published_fps, str(cam_id)))
    except Exception as exc:
        log.warning("Runtime metadata update failed: %s", exc)


class CameraWorker:
    def __init__(self, cam, r):
        self.cam_id = str(cam["id"]); self.sid = cam["stream_id"]; self.name = cam["name"]; self.url = cam["rtsp_url"]
        self.codec = cam.get("codec") or "unknown"; self.adapter = adapter_for(cam); self.r = r; self.interval = 1.0 / FRAME_FPS

    def _open(self): return self.adapter.open()

    def _reconnect(self):
        delay = 2
        attempts = 0
        while attempts < 6:
            attempts += 1
            log.info("%s: reconnecting in %ss (attempt %s/6)", self.name, delay, attempts)
            time.sleep(delay)
            cap = self._open()
            if cap.isOpened():
                log.info("%s: reconnected", self.name)
                return cap
            cap.release(); delay = min(delay * 2, RECONNECT_MAX_DELAY)
        return None

    def _encode(self, frame):
        ok, buf = cv2.imencode(".jpg", frame, ENCODE_PARAMS)
        if not ok: raise RuntimeError("JPEG encoding failed")
        return base64.b64encode(buf).decode()

    def _publish(self, frame_b64, pts_ms, w, h):
        now = datetime.now(timezone.utc).isoformat().encode()
        fields = {b"schema_version": b"1.0", b"event_id": str(uuid.uuid4()).encode(), b"event_type": b"frame", b"cam_id": self.cam_id.encode(), b"stream_id": str(self.sid).encode(), b"frame": frame_b64.encode(), b"source_ts": b"", b"ingested_at": now, b"pts_ms": str(int(pts_ms)).encode(), b"width": str(w).encode(), b"height": str(h).encode(), b"codec": self.codec.encode()}
        self.r.xadd(STREAM_KEY, fields, maxlen=STREAM_MAX, approximate=True); self.r.set(f"snapshot:{self.cam_id}", frame_b64.encode(), ex=10)

    def _stream_fps(self, cap):
        reported = cap.get(cv2.CAP_PROP_FPS) if cap.isOpened() else 0.0
        return reported if 0 < reported <= 120 else None

    def run(self):
        log.info("Starting %s → %s", self.name, self.url)
        cap = self._open()
        source_fps = self._stream_fps(cap)
        if not cap.isOpened():
            set_status(self.cam_id, "offline")
        else:
            set_status(self.cam_id, "active")
        last_t = 0.0; fail_streak = 0; prev_pts = None; observed_started = time.monotonic(); observed_frames = 0; published_frames = 0; last_health_write = 0.0
        try:
            while True:
                if cap is None or not cap.isOpened():
                    set_status(self.cam_id, "offline")
                    cap = self._reconnect()
                    if cap is None:
                        time.sleep(10)
                        continue
                    source_fps = self._stream_fps(cap); set_status(self.cam_id, "active")
                    fail_streak = 0; prev_pts = None
                    observed_started = time.monotonic(); observed_frames = 0; published_frames = 0; last_health_write = 0.0
                ret, frame = cap.read()
                if not ret:
                    fail_streak += 1
                    if fail_streak >= 15:
                        cap.release(); cap = None; set_status(self.cam_id, "reconnecting")
                    time.sleep(0.05); continue
                fail_streak = 0; observed_frames += 1; pts_ms = cap.get(cv2.CAP_PROP_POS_MSEC); now = time.monotonic()
                if now - last_t < self.interval: continue
                last_t = now
                if prev_pts is not None and pts_ms < prev_pts - 1000:
                    log.info("%s: PTS discontinuity %.0f→%.0f; signalling reset", self.name, prev_pts, pts_ms)
                    self.r.xadd("cam_resets", {b"cam_id": self.cam_id.encode(), b"stream_id": str(self.sid).encode()}, maxlen=500, approximate=True)
                prev_pts = pts_ms; h, w = frame.shape[:2]
                try: self._publish(self._encode(frame), pts_ms, w, h); published_frames += 1
                except Exception as exc: log.error("%s: publish error: %s", self.name, exc)
                if now - last_health_write >= 30:
                    elapsed = max(now - observed_started, 0.001)
                    update_runtime_observation(self.cam_id, w, h, source_fps, round(observed_frames / elapsed, 2), round(published_frames / elapsed, 2), self.codec)
                    observed_started = now; observed_frames = 0; published_frames = 0; last_health_write = now
        finally:
            if cap is not None: cap.release()
            set_status(self.cam_id, "offline")


def run_worker(cam):
    CameraWorker(cam, redis.from_url(REDIS_URL, decode_responses=False)).run()


def start_camera_worker(cam):
    process = Process(target=run_worker, args=(cam,), daemon=True); process.start(); log.info("Started ingestion worker for %s (%s)", cam["name"], str(cam["id"])[:8]); return process


def main():
    log.info("Ingestion service starting …")
    from test_runner import supervise as supervise_test_sessions
    threading.Thread(target=supervise_test_sessions, name="test-session-supervisor", daemon=True).start()
    from catalogue_sync import sync as catalogue_sync
    for attempt in range(20):
        try: psycopg2.connect(DB_URL).close(); break
        except Exception as exc: log.info("Waiting for DB (%s/20): %s", attempt + 1, exc); time.sleep(3)
    n = catalogue_sync()
    if n == 0: time.sleep(10); n = catalogue_sync()
    cams = get_cameras()
    if not cams: log.critical("No active cameras in DB after catalogue sync. Exiting."); sys.exit(1)
    log.info("Starting %s camera workers …", len(cams)); procs = {}
    for cam in cams: procs[str(cam["id"])] = (cam, start_camera_worker(cam)); time.sleep(0.3)
    last_catalogue_sync = time.monotonic()
    while True:
        time.sleep(30)
        if time.monotonic() - last_catalogue_sync >= CATALOGUE_SYNC_INTERVAL:
            try: catalogue_sync()
            except Exception as exc: log.warning("Catalogue sync during reconcile failed: %s", exc)
            last_catalogue_sync = time.monotonic()
        try: wanted = {str(cam["id"]): cam for cam in get_cameras()}
        except Exception as exc: log.warning("Registry reconcile skipped: %s", exc); continue
        for cam_id, (cam, process) in list(procs.items()):
            replacement = wanted.get(cam_id)
            if replacement is None:
                process.terminate(); process.join(timeout=5); del procs[cam_id]; continue
            if replacement["rtsp_url"] != cam["rtsp_url"]:
                process.terminate(); process.join(timeout=5); procs[cam_id] = (replacement, start_camera_worker(replacement)); continue
            if not process.is_alive():
                log.warning("Worker %s died (exit %s). Restarting …", cam["name"], process.exitcode); procs[cam_id] = (replacement, start_camera_worker(replacement))
            wanted.pop(cam_id, None)
        for cam_id, cam in wanted.items(): procs[cam_id] = (cam, start_camera_worker(cam))

if __name__ == "__main__": main()
