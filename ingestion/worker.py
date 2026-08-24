#!/usr/bin/env python3
"""
Ingestion Worker — Live RTSP compliance build
• Forces TCP transport (no UDP)
• Publishes PTS (not wall-clock) with every frame
• Exponential backoff on reconnect (2 s → 30 s cap)
• Treats decoder warnings as non-fatal
• Syncs camera list from /api/ingest before starting
"""
import os, sys, time, base64, logging
from multiprocessing import Process

# ── CRITICAL: must be set BEFORE cv2 is imported anywhere ────────────────────
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import cv2
import numpy as np
import redis
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [INGEST][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REDIS_URL   = os.getenv("REDIS_URL",   "redis://localhost:6379")
DB_URL      = os.getenv("DATABASE_URL","")
FRAME_FPS   = float(os.getenv("FRAME_FPS",  "3"))
JPEG_Q      = int(os.getenv("JPEG_QUALITY", "70"))
MAX_CAMS    = int(os.getenv("MAX_CONCURRENT_CAMERAS", "30"))
STREAM_KEY  = "raw_frames"
STREAM_MAX  = 3000
ENCODE_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q]


# ─── Database helpers ─────────────────────────────────────────────────────────
def get_cameras():
    conn = psycopg2.connect(DB_URL)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, name, stream_id, rtsp_url, codec "
            "FROM cameras WHERE status = 'active' ORDER BY stream_id LIMIT %s",
            (MAX_CAMS,)
        )
        cams = [dict(r) for r in cur.fetchall()]
    conn.close()
    return cams


def set_status(cam_id, status):
    try:
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute("UPDATE cameras SET status=%s, last_seen_at=NOW() "
                        "WHERE id=%s", (status, str(cam_id)))
        conn.commit(); conn.close()
    except Exception as e:
        log.warning(f"Status update failed: {e}")


# ─── Per-camera worker ────────────────────────────────────────────────────────
class CameraWorker:
    def __init__(self, cam: dict, r: redis.Redis):
        self.cam_id   = str(cam["id"])
        self.sid      = cam["stream_id"]
        self.name     = cam["name"]
        self.url      = cam["rtsp_url"]
        self.codec    = cam.get("codec", "H.264")
        self.r        = r
        self.interval = 1.0 / FRAME_FPS

    # ── Open with TCP forced ──────────────────────────────────────────────────
    def _open(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        return cap

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
            b"cam_id":    self.cam_id.encode(),
            b"stream_id": str(self.sid).encode(),
            b"frame":     frame_b64.encode(),
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

        cap.release()
        set_status(self.cam_id, "offline")


# ─── Process entry point ──────────────────────────────────────────────────────
def run_worker(cam: dict):
    r = redis.from_url(REDIS_URL, decode_responses=False)
    CameraWorker(cam, r).run()


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

    # 3. Spawn one process per camera
    procs = []
    for cam in cams:
        p = Process(target=run_worker, args=(cam,), daemon=True)
        p.start()
        procs.append((cam, p))
        time.sleep(0.3)   # stagger to avoid thundering herd on RTSP server

    # 4. Monitor + restart dead workers
    while True:
        time.sleep(30)
        for i, (cam, p) in enumerate(procs):
            if not p.is_alive():
                log.warning(f"Worker {cam['name']} died (exit {p.exitcode}). Restarting …")
                np2 = Process(target=run_worker, args=(cam,), daemon=True)
                np2.start()
                procs[i] = (cam, np2)


if __name__ == "__main__":
    main()
