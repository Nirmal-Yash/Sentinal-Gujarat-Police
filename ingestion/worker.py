#!/usr/bin/env python3
"""Ingestion Worker — live RTSP ingestion with P0 operational telemetry."""
import os, sys, time, base64, logging, uuid, threading
from datetime import datetime, timezone
from multiprocessing import Process

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import cv2
import numpy as np
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from stream_adapters import adapter_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s [INGEST][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DB_URL = os.getenv("DATABASE_URL", "")
SOURCE_MAX_FPS = max(1.0, float(os.getenv("SOURCE_MAX_FPS", "15")))
FRAME_GATE_ENABLED = os.getenv("FRAME_GATE_ENABLED", "true").lower() == "true"
MOTION_THRESHOLD = max(0.0, float(os.getenv("FRAME_GATE_MOTION_THRESHOLD", "4.0")))
IDLE_MAX_SECS = max(1.0, float(os.getenv("FRAME_GATE_IDLE_SECS", "10")))
THUMBNAIL_SIZE = max(16, int(os.getenv("FRAME_GATE_THUMBNAIL_SIZE", "160")))
ALIVE_KEY = os.getenv("CAMERA_ALIVE_KEY", "camera_alive")
ALIVE_INTERVAL = max(0.5, float(os.getenv("CAMERA_ALIVE_INTERVAL_SECS", "1")))
RAW_STREAM_MAX = max(100, int(os.getenv("RAW_FRAME_STREAM_MAXLEN", "500")))
def _category_interval(name: str, default_fps: float) -> float:
    env_name = {
        "highway": "PROCESSING_FPS_HIGHWAY",
        "pedestrian": "PROCESSING_FPS_PEDESTRIAN",
        "static": "PROCESSING_FPS_STATIC",
    }.get(name)
    try:
        fps = float(os.getenv(env_name, str(default_fps))) if env_name else default_fps
    except (TypeError, ValueError):
        fps = default_fps
    return 1.0 / max(0.25, fps)

CATEGORY_INTERVALS = {
    "highway": _category_interval("highway", 3.33),
    "pedestrian": _category_interval("pedestrian", 2.0),
    "static": _category_interval("static", 1.25),
}
JPEG_Q = int(os.getenv("JPEG_QUALITY", "70"))
SNAPSHOT_TTL = max(10, int(os.getenv("SNAPSHOT_TTL_SECS", "30")))
MAX_CAMS = max(1, int(os.getenv("MAX_CONCURRENT_CAMERAS", "50")))
TEST_SESSION_POLL_SECS = max(1.0, float(os.getenv("TEST_SESSION_POLL_SECS", "2")))
CATALOGUE_SYNC_INTERVAL = max(30, int(os.getenv("CATALOGUE_SYNC_INTERVAL", "300")))
RECONNECT_MAX_DELAY = max(5, int(os.getenv("RECONNECT_MAX_DELAY", "30")))
STREAM_KEY = "raw_frames"
STREAM_MAX = 3000
RESET_STREAM = "cam_resets"
RESET_MAX = 500
ENCODE_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q]
SCENE_DISCONTINUITY_MS = max(1000, int(os.getenv("SCENE_DISCONTINUITY_MS", "5000")))


def test_mode_active():
    try:
        with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
            cur.execute("SELECT EXISTS(SELECT 1 FROM test_sessions WHERE status IN ('starting','active'))")
            return bool(cur.fetchone()[0])
    except Exception as exc:
        log.warning("Test-mode status check failed: %s", exc)
        return False


def stop_production_workers(procs):
    for key, (_, proc) in list(procs.items()):
        if proc.is_alive():
            log.info("Test mode active; stopping production ingestion worker %s", key[:8])
            proc.terminate()
            proc.join(timeout=3)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=1)
    procs.clear()


def get_cameras():
    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id,name,stream_id,rtsp_url,codec,COALESCE(processing_fps_category,'pedestrian') AS processing_fps_category FROM cameras WHERE status='active' AND rtsp_url IS NOT NULL AND rtsp_url<>'' ORDER BY stream_id LIMIT %s", (MAX_CAMS,))
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


def increment_reconnect(cam_id):
    try:
        with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
            cur.execute("UPDATE cameras SET reconnect_count=COALESCE(reconnect_count,0)+1,updated_at=NOW() WHERE id=%s", (str(cam_id),))
    except Exception as exc:
        log.warning("Reconnect counter update failed: %s", exc)


def increment_decode_failure(cam_id):
    try:
        with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
            cur.execute("UPDATE cameras SET decode_failure_count=COALESCE(decode_failure_count,0)+1,updated_at=NOW() WHERE id=%s", (str(cam_id),))
    except Exception as exc:
        log.warning("Decode-failure counter update failed: %s", exc)


def update_runtime_observation(cam_id, width, height, source_fps, decode_fps, published_fps, codec, last_pts_ms, status="active"):
    """Persist observed dimensions/rates and explicit frame-health evidence."""
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
        self.cam_id = str(cam["id"])
        self.sid = cam["stream_id"]
        self.name = cam["name"]
        self.url = cam["rtsp_url"]
        self.codec = cam.get("codec") or "unknown"
        self.adapter = adapter_for(cam)
        self.r = r
        category = str(cam.get("processing_fps_category") or "pedestrian").lower()
        self.processing_category = category if category in CATEGORY_INTERVALS else "pedestrian"
        self.interval = CATEGORY_INTERVALS[self.processing_category]
        self.prev_thumb = None
        self.last_alive = 0.0
        self.last_forwarded = 0.0

    def _open(self):
        log.info("Opening RTSP/TCP source for %s", self.name)
        return self.adapter.open()

    def _reconnect(self):
        delay = 2
        attempts = 0
        increment_reconnect(self.cam_id)
        while attempts < 6:
            attempts += 1
            log.info("%s: reconnecting in %ss (attempt %s/6)", self.name, delay, attempts)
            time.sleep(delay)
            cap = self._open()
            if cap.isOpened():
                log.info("%s: reconnected", self.name)
                return cap
            cap.release()
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        log.warning("%s: reconnect cycle exhausted; entering offline wait", self.name)
        return None

    def _encode(self, frame):
        ok, buf = cv2.imencode(".jpg", frame, ENCODE_PARAMS)
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return base64.b64encode(buf).decode()

    def _scene_activity(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        thumb = cv2.resize(gray, (THUMBNAIL_SIZE, max(1, round(THUMBNAIL_SIZE*0.5625))), interpolation=cv2.INTER_AREA)
        activity = 255.0 if self.prev_thumb is None else float(np.mean(cv2.absdiff(thumb, self.prev_thumb)))
        self.prev_thumb = thumb
        return activity

    def _camera_alive(self):
        if time.monotonic() - self.last_alive >= ALIVE_INTERVAL:
            self.r.hset(ALIVE_KEY, self.cam_id, str(time.time()))
            self.last_alive = time.monotonic()

    def _should_forward(self, frame):
        activity = self._scene_activity(frame) if FRAME_GATE_ENABLED else 255.0
        elapsed = time.monotonic() - self.last_forwarded
        if elapsed < self.interval:
            return False
        if not FRAME_GATE_ENABLED or activity >= MOTION_THRESHOLD or elapsed >= IDLE_MAX_SECS:
            self.last_forwarded = time.monotonic()
            return True
        return False

    def _publish(self, frame_b64, pts_ms, w, h):
        now = datetime.now(timezone.utc).isoformat().encode()
        fields = {
            b"schema_version": b"1.0",
            b"event_id": str(uuid.uuid4()).encode(),
            b"event_type": b"frame",
            b"cam_id": self.cam_id.encode(),
            b"stream_id": str(self.sid).encode(),
            b"frame": frame_b64.encode(),
            b"source_ts": now,
            b"ingested_at": now,
            b"pts_ms": str(int(pts_ms)).encode(),
            b"width": str(w).encode(),
            b"height": str(h).encode(),
            b"codec": self.codec.encode(),
            b"processing_fps_category": self.processing_category.encode(),
            b"processing_interval_ms": str(int(self.interval*1000)).encode(),
        }
        self.r.xadd(STREAM_KEY, fields, maxlen=RAW_STREAM_MAX, approximate=True)
        # Keep both canonical registry and provider keys.  The UUID is the API
        # identity; the provider alias is a cheap recovery path for streams
        # that were restarted while a registry row was being refreshed.
        encoded = frame_b64.encode()
        self.r.set(f"snapshot:{self.cam_id}", encoded, ex=SNAPSHOT_TTL)
        self.r.set(f"snapshot:cam{int(self.sid):02d}", encoded, ex=SNAPSHOT_TTL)

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
            log.info("%s: connected; source_fps=%s", self.name, source_fps or "unknown")

        last_publish = 0.0
        fail_streak = 0
        prev_pts = None
        observed_started = time.monotonic()
        observed_frames = 0
        published_frames = 0
        last_health_write = 0.0

        try:
            while True:
                if cap is None or not cap.isOpened():
                    set_status(self.cam_id, "reconnecting")
                    cap = self._reconnect()
                    if cap is None:
                        set_status(self.cam_id, "offline")
                        time.sleep(10)
                        continue

                    source_fps = self._stream_fps(cap)
                    set_status(self.cam_id, "active")
                    fail_streak = 0
                    prev_pts = None
                    observed_started = time.monotonic()
                    observed_frames = 0
                    published_frames = 0
                    last_health_write = 0.0

                ret, frame = cap.read()
                if not ret:
                    fail_streak += 1
                    if fail_streak == 1:
                        increment_decode_failure(self.cam_id)
                    if fail_streak >= 15:
                        log.warning("%s: 15 consecutive frame-read failures; reconnecting", self.name)
                        cap.release()
                        cap = None
                        set_status(self.cam_id, "reconnecting")
                    time.sleep(0.05)
                    continue

                fail_streak = 0
                observed_frames += 1
                self._camera_alive()
                pts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                if not pts_ms or pts_ms < 0:
                    pts_ms = 0.0

                now = time.monotonic()
                self._camera_alive()
                if not self._should_forward(frame):
                    continue
                last_publish = now

                if prev_pts is not None:
                    delta = pts_ms - prev_pts
                    if delta < 0 or delta > SCENE_DISCONTINUITY_MS:
                        log.info(
                            "%s: PTS discontinuity %.0f→%.0f (delta=%.0fms); resetting downstream state",
                            self.name,
                            prev_pts,
                            pts_ms,
                            delta,
                        )
                        self.r.xadd(
                            RESET_STREAM,
                            {
                                b"cam_id": self.cam_id.encode(),
                                b"stream_id": str(self.sid).encode(),
                                b"reason": b"pts_discontinuity",
                                b"previous_pts_ms": str(int(prev_pts)).encode(),
                                b"current_pts_ms": str(int(pts_ms)).encode(),
                            },
                            maxlen=RESET_MAX,
                            approximate=True,
                        )
                prev_pts = pts_ms

                h, w = frame.shape[:2]
                try:
                    self._publish(self._encode(frame), pts_ms, w, h)
                    published_frames += 1
                except Exception as exc:
                    log.error("%s: publish error: %s", self.name, exc)

                if now - last_health_write >= 30:
                    elapsed = max(now - observed_started, 0.001)
                    decode_rate = observed_frames / elapsed
                    publish_rate = published_frames / elapsed
                    update_runtime_observation(
                        self.cam_id,
                        w,
                        h,
                        source_fps,
                        round(decode_rate, 2),
                        round(publish_rate, 2),
                        self.codec,
                        int(pts_ms),
                    )
                    log.info(
                        "%s: telemetry frames=%s published=%s decode_fps=%.2f publish_fps=%.2f pts=%sms",
                        self.name,
                        observed_frames,
                        published_frames,
                        decode_rate,
                        publish_rate,
                        int(pts_ms),
                    )
                    observed_started = now
                    observed_frames = 0
                    published_frames = 0
                    last_health_write = now

        finally:
            if cap is not None:
                cap.release()
            set_status(self.cam_id, "offline")


def run_worker(cam):
    CameraWorker(
        cam,
        redis.from_url(
            REDIS_URL,
            decode_responses=False,
        ),
    ).run()


def start_camera_worker(cam):
    process = Process(
        target=run_worker,
        args=(cam,),
        daemon=True,
    )
    process.start()
    log.info(
        "Started ingestion worker for %s (%s)",
        cam["name"],
        str(cam["id"])[:8],
    )
    return process


def main():
    log.info("Ingestion service starting …")

    from test_runner import supervise as supervise_test_sessions
    threading.Thread(target=supervise_test_sessions, name="test-session-supervisor", daemon=True).start()
    from catalogue_sync import sync as catalogue_sync

    for attempt in range(20):
        try:
            psycopg2.connect(DB_URL).close()
            break
        except Exception as exc:
            log.info("Waiting for DB (%s/20): %s", attempt + 1, exc)
            time.sleep(3)

    procs = {}
    last_catalogue_sync = 0.0
    test_was_active = False

    while True:
        active_test = test_mode_active()
        if active_test:
            if not test_was_active:
                log.info("ISOLATED TEST MODE ACTIVE — production CCTV ingestion paused")
                stop_production_workers(procs)
                test_was_active = True
            time.sleep(TEST_SESSION_POLL_SECS)
            continue

        if test_was_active:
            log.info("ISOLATED TEST MODE ENDED — resuming production CCTV ingestion")
            test_was_active = False
            last_catalogue_sync = 0.0

        if not procs:
            try:
                n = catalogue_sync()
                if n == 0:
                    log.critical("Current CCTV catalogue unavailable; no retired-source fallback is permitted")
                    time.sleep(10)
                    continue
            except Exception as exc:
                log.error("CCTV catalogue sync failed: %s", exc, exc_info=True)
                time.sleep(5)
                continue

            cams = get_cameras()
            if not cams:
                log.critical("No active cameras in DB after current CCTV catalogue sync. Retrying.")
                time.sleep(5)
                continue

            log.info("Starting %s production camera workers …", len(cams))
            for cam in cams:
                procs[str(cam["id"])] = (cam, start_camera_worker(cam))
                time.sleep(0.3)
            last_catalogue_sync = time.monotonic()

        time.sleep(2)
        if test_mode_active():
            continue

        if time.monotonic() - last_catalogue_sync >= CATALOGUE_SYNC_INTERVAL:
            try:
                catalogue_sync()
                last_catalogue_sync = time.monotonic()
            except Exception as exc:
                log.warning("Periodic CCTV catalogue sync failed: %s", exc)

        for key, (cam, proc) in list(procs.items()):
            if not proc.is_alive():
                procs.pop(key, None)
                set_status(str(cam["id"]), "reconnecting")
                if not test_mode_active():
                    procs[key] = (cam, start_camera_worker(cam))

if __name__ == "__main__":
    main()
