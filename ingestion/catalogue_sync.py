#!/usr/bin/env python3
"""
Catalogue Sync
Fetches http://<host>/api/ingest and upserts all cameras into PostgreSQL.
Run once at startup, then periodically.
"""
import os, time, logging
import requests
import psycopg2
from psycopg2.extras import execute_values

log = logging.getLogger("catalogue_sync")

INGEST_API = os.getenv("INGEST_API", "http://live.corp8.cloud/api/ingest")
RTSP_HOST  = os.getenv("RTSP_HOST",  "live.corp8.cloud")
DB_URL     = os.getenv("DATABASE_URL", "")
SYNC_INTERVAL = int(os.getenv("CATALOGUE_SYNC_INTERVAL", "300"))


def _build_urls(cam: dict) -> dict:
    """Build all three stream URLs from catalogue entry."""
    sid = cam.get("id")
    rtsp = cam.get("rtsp_url") or f"rtsp://{RTSP_HOST}:8554/stream/{sid}"
    hls  = cam.get("hls_url")  or f"http://{RTSP_HOST}/live/stream/{sid}/index.m3u8"
    whep = cam.get("whep_url") or f"http://{RTSP_HOST}:8889/stream/{sid}/whep"
    return {"rtsp": rtsp, "hls": hls, "whep": whep}


def fetch_catalogue(retries: int = 5) -> list:
    delay = 2
    for attempt in range(retries):
        try:
            r = requests.get(INGEST_API, timeout=10)
            r.raise_for_status()
            data = r.json()
            # Handle both list and {"cameras": [...]} shapes
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("cameras") or data.get("streams") or list(data.values())
        except Exception as e:
            log.warning(f"Catalogue fetch attempt {attempt+1}/{retries} failed: {e}")
            time.sleep(delay)
            delay = min(delay * 2, 30)
    return []


def sync(conn=None) -> int:
    """Upsert cameras from /api/ingest. Returns number of cameras synced."""
    cameras = fetch_catalogue()
    if not cameras:
        log.warning("Empty catalogue — skipping sync")
        return 0

    close_after = conn is None
    if conn is None:
        conn = psycopg2.connect(DB_URL)

    rows = []
    for cam in cameras:
        sid  = int(cam.get("id", 0))
        urls = _build_urls(cam)
        name = cam.get("location") or cam.get("name") or f"Camera {sid}"
        rows.append((
            sid,
            name,
            cam.get("location", ""),
            float(cam.get("lat", 22.3039)),
            float(cam.get("lng",  70.8022)),
            urls["rtsp"],
            urls["hls"],
            urls["whep"],
            str(cam.get("codec", "H.264")),
            int(cam.get("width",  1280)),
            int(cam.get("height", 720)),
            float(cam.get("fps",  25)),
            "active" if cam.get("live", True) else "offline",
        ))

    sql = """
        INSERT INTO cameras
          (stream_id, name, location, lat, lng,
           rtsp_url, hls_url, whep_url,
           codec, width, height, fps, status, last_seen_at)
        VALUES %s
        ON CONFLICT (stream_id) DO UPDATE SET
          name         = EXCLUDED.name,
          location     = EXCLUDED.location,
          lat          = EXCLUDED.lat,
          lng          = EXCLUDED.lng,
          rtsp_url     = EXCLUDED.rtsp_url,
          hls_url      = EXCLUDED.hls_url,
          whep_url     = EXCLUDED.whep_url,
          codec        = EXCLUDED.codec,
          width        = EXCLUDED.width,
          height       = EXCLUDED.height,
          fps          = EXCLUDED.fps,
          status       = EXCLUDED.status,
          last_seen_at = NOW()
    """
    template = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())"

    with conn.cursor() as cur:
        execute_values(cur, sql, rows, template=template)
    conn.commit()

    if close_after:
        conn.close()

    log.info(f"Catalogue sync: {len(rows)} cameras upserted from {INGEST_API}")
    return len(rows)


def run_loop():
    """Sync once on startup then every SYNC_INTERVAL seconds."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [CATALOGUE][%(levelname)s] %(message)s")
    # Wait for DB
    for _ in range(20):
        try:
            conn = psycopg2.connect(DB_URL)
            conn.close()
            break
        except Exception as e:
            log.info(f"Waiting for DB: {e}")
            time.sleep(3)

    while True:
        try:
            sync()
        except Exception as e:
            log.error(f"Sync error: {e}")
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    run_loop()
