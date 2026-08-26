#!/usr/bin/env python3
"""
Ingestion Worker — Live RTSP compliance build
• Forces TCP transport (no UDP)
• Publishes PTS (not wall-clock) with every frame
• Exponential backoff on reconnect (2 s → 30 s cap)
• Treats decoder warnings as non-fatal
• Syncs camera list from /api/ingest before starting
"""
import os, sys, time, base64, logging, uuid
from datetime import datetime, timezone
from multiprocessing import Process

# ── CRITICAL: must be set BEFORE cv2 is imported anywhere ────────────────────
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import cv2
import numpy as np
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from stream_adapters import adapter_for

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [INGEST][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REDIS_URL   = os.getenv("REDIS_URL",   "redis://localhost:6379")
DB_URL      = os.getenv("DATABASE_URL","")
FRAME_FPS   = float(os.getenv("FRAME_FPS",  "3"))
JPEG_Q      = int(os.getenv("JPEG_QUALITY", "70"))
MAX_CAMS    = int(os.getenv("MAX_CONCURRENT_CAMERAS", "30"))
CATALOGUE_SYNC_INTERVAL = int(os.getenv("CATALOGUE_SYNC_INTERVAL", "300"))
STREAM_KEY  = "raw_frames"
STREAM_MAX  = 3000
ENCODE_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q]


# ─── Database helpers ─────────────────────────────────────────────────────────
def get_cameras():
    conn = psycopg2.connect(DB_URL)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, name, stream_id, rtsp_url, codec "
            "FROM cameras WHERE status = 'active' AND rtsp_url IS NOT NULL AND rtsp_url <> '' "
            "ORDER BY stream_id LIMIT %s",
            (MAX_CAMS,)
        )
        cams = [dict(r) for r in cur.fetchall()]
    conn.close()
    return cams


def set_status(cam_id, status):
    """Record observed connection health without changing registry lifecycle state."""
    health = {"active": "healthy", "reconnecting": "reconnecting", "offline": "offline"}.get(status, "unknown")
    connectivity = {"active": "connected", "reconnecting": "reconnecting", "offline": "disconnected"}.get(status, "unknown")
    try:
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute("""UPDATE cameras SET connectivity_status=%s, health_status=%s,
                           last_seen_at=CASE WHEN %s='active' THEN NOW() ELSE last_seen_at END,
                           updated_at=NOW() WHERE id=%s""",
                        (connectivity, health, status, str(cam_id)))
        conn.commit(); conn.close()
    except Exception as e:
        log.warning(f"Status update failed: {e}")


def update_runtime_observation(cam_id, width, height, fps, codec, status="active"):
    """Keep measured stream observations separate from registry configuration."""
    try:
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE cameras SET observed_width=%s, observed_height=%s,
                    observed_fps=%s, observed_codec=%s, observed_at=NOW(),
                    last_frame_at=NOW(), last_seen_at=NOW(), status=%s,
                    health_status=CASE WHEN %s='active' THEN 'healthy' ELSE %s END,
                    connectivity_status=CASE WHEN %s='active' THEN 'connected' ELSE %s END,
                    updated_at=NOW()
                WHERE id=%s
            """, (width, height, fps, codec, status, status, status, status, str(cam_id)))
        conn.commit(); conn.close()
    except Exception as e:
        log.warning(f"Runtime metadata update failed: {e}")


# ─── Per-camera worker ────────────────────────────────────────────────────────
class CameraWorker:
    def __init__(self, cam: dict, r: redis.Redis):
        self.cam_id   = str(cam["id"])
        self.sid      = cam["stream_id"]
        self.name     = cam["name"]
        self.url      = cam["rtsp_url"]
        self.codec    = cam.get("codec") or "unknown"
        self.adapter  = adapter_for(cam)
        self.r        = r
        self.interval = 1.0 / FRAME_FPS

    # ── Open with TCP forced ──────────────────────────────────────────────────
    def _open(self) -> cv2.VideoCapture:
        return self.adapter.open()

    # ── Reconnect with exponential backoff ────────────────────────────────────
    def _reconnect(self) -> cv2.VideoCapture:
        delay = 2
        while True:
            log.info(f"{self.name}: reconnecting in {delay}s …")
            time.sleep(delay)
            cap = self._open()
            if cap.isOpened():
                log.info(f"{self.name}: reconnected")
                return cap
            cap.release()
            delay = min(delay * 2, 30)

    def _encode(self, frame) -> str:
        _, buf = cv2.imencode(".jpg", frame, ENCODE_PARAMS)
        return base64.b64encode(buf).decode()

    def _publish(self, frame_b64: str, pts_ms: float, w: int, h: int):
        fields = {
            b"schema_version": b"1.0",
            b"event_id": str(uuid.uuid4()).encode(),
            b"event_type": b"frame",
            b"cam_id":    self.cam_id.encode(),
            b"stream_id": str(self.sid).encode(),
            b"frame":     frame_b64.encode(),
            # OpenCV does not expose a trustworthy RTSP source clock.  Do not
            # relabel worker time as source time; downstream sees it separately.
            b"source_ts": b"",
            b"ingested_at": datetime.now(timezone.utc).isoformat().encode(),
            b"pts_ms":    str(int(pts_ms)).encode(),   # PTS — not wall clock
            b"width":     str(w).encode(),
            b"height":    str(h).encode(),
            b"codec":     self.codec.encode(),
        }
        self.r.xadd(STREAM_KEY, fields, maxlen=STREAM_MAX, approximate=True)
        # Snapshot for dashboard (10 s TTL)
        self.r.set(f"snapshot:{self.cam_id}", frame_b64.encode(), ex=10)

    def run(self):
        log.info(f"Starting {self.name} → {self.url}")
        set_status(self.cam_id, "active")
        cap         = self._open()
        last_t      = 0.0
        fail_streak = 0
        prev_pts    = None
        observed_started = time.monotonic()
        observed_frames  = 0
        last_health_write = 0.0

        while True:
            ret, frame = cap.read()

            # ── Decoder warnings / NAL errors are non-fatal ───────────────────
            if not ret:
                fail_streak += 1
                if fail_streak >= 15:
                    cap.release()
                    set_status(self.cam_id, "reconnecting")
                    cap         = self._reconnect()
                    fail_streak = 0
                    prev_pts    = None  # reset PTS tracking after reconnect
                    set_status(self.cam_id, "active")
                time.sleep(0.05)
                continue

            fail_streak = 0
            observed_frames += 1

            # ── Use PTS, not wall-clock (resource page §3) ────────────────────
            pts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)

            # ── Frame-rate throttle ───────────────────────────────────────────
            now = time.monotonic()
            if now - last_t < self.interval:
                continue
            last_t = now

            # ── Scene discontinuity detection (loop point / camera reboot) ────
            if prev_pts is not None and pts_ms < prev_pts - 1000:
                log.info(f"{self.name}: PTS jumped {prev_pts:.0f}→{pts_ms:.0f} "
                         "(scene discontinuity) — signalling reset")
                # Publish a special reset marker so AI workers can reset trackers
                self.r.xadd("cam_resets",
                             {b"cam_id": self.cam_id.encode(),
                              b"stream_id": str(self.sid).encode()},
                             maxlen=500, approximate=True)
            prev_pts = pts_ms

            h, w = frame.shape[:2]
            try:
                self._publish(self._encode(frame), pts_ms, w, h)
            except Exception as e:
                log.error(f"{self.name}: publish error: {e}")

            # A bounded, measured metadata refresh prevents repeated probes.
            if now - last_health_write >= 30:
                elapsed = max(now - observed_started, 0.001)
                update_runtime_observation(
                    self.cam_id, w, h, round(observed_frames / elapsed, 2), self.codec)
                observed_started, observed_frames, last_health_write = now, 0, now

        cap.release()
        set_status(self.cam_id, "offline")


# ─── Process entry point ──────────────────────────────────────────────────────
def run_worker(cam: dict):
    r = redis.from_url(REDIS_URL, decode_responses=False)
    CameraWorker(cam, r).run()


def start_camera_worker(cam: dict) -> Process:
    process = Process(target=run_worker, args=(cam,), daemon=True)
    process.start()
    log.info("Started ingestion worker for %s (%s)", cam["name"], str(cam["id"])[:8])
    return process


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    log.info("Ingestion service starting …")

    # 1. Sync camera catalogue first
    from catalogue_sync import sync as catalogue_sync
    for attempt in range(20):
        try:
            psycopg2.connect(DB_URL).close()
            break
        except Exception as e:
            log.info(f"Waiting for DB ({attempt+1}/20): {e}")
            time.sleep(3)

    n = catalogue_sync()
    if n == 0:
        log.warning("Catalogue returned 0 cameras — retrying in 10 s")
        time.sleep(10)
        n = catalogue_sync()

    # 2. Load cameras from DB
    cams = get_cameras()
    if not cams:
        log.critical("No active cameras in DB after catalogue sync. Exiting.")
        sys.exit(1)

    log.info(f"Starting {len(cams)} camera workers …")

    # 3. Spawn one process per active registry camera.  The supervisor below
    # reconciles this set, so approved onboarding does not require a restart.
    procs = {}
    for cam in cams:
        procs[str(cam["id"])] = (cam, start_camera_worker(cam))
        time.sleep(0.3)   # stagger to avoid thundering herd on RTSP server

    # 4. Monitor/restart workers and reconcile registry source changes.
    last_catalogue_sync = time.monotonic()
    while True:
        time.sleep(30)
        if time.monotonic() - last_catalogue_sync >= CATALOGUE_SYNC_INTERVAL:
            try:
                catalogue_sync()
            except Exception as exc:
                log.warning("Catalogue sync during reconcile failed: %s", exc)
            last_catalogue_sync = time.monotonic()
        try:
            wanted = {str(cam["id"]): cam for cam in get_cameras()}
        except Exception as exc:
            log.warning("Registry reconcile skipped: %s", exc)
            continue

        for cam_id, (cam, process) in list(procs.items()):
            replacement = wanted.get(cam_id)
            if replacement is None:
                log.info("Stopping worker for deactivated/removed camera %s", cam["name"])
                process.terminate(); process.join(timeout=5)
                del procs[cam_id]
                continue
            if replacement["rtsp_url"] != cam["rtsp_url"]:
                log.info("Restarting worker for updated source %s", cam["name"])
                process.terminate(); process.join(timeout=5)
                procs[cam_id] = (replacement, start_camera_worker(replacement))
                continue
            if not process.is_alive():
                log.warning(f"Worker {cam['name']} died (exit {process.exitcode}). Restarting …")
                procs[cam_id] = (replacement, start_camera_worker(replacement))
            wanted.pop(cam_id, None)

        for cam_id, cam in wanted.items():
            procs[cam_id] = (cam, start_camera_worker(cam))


if __name__ == "__main__":
    main()
