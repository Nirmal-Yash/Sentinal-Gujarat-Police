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
    hls = cam.get("hls_live_url") or cam.get("hls_url") or ""
    if hls and not hls.startswith(("http://", "https://")):
        hls = f"https://{RTSP_HOST}/{hls.lstrip('/')}"
    hls = hls or f"https://{RTSP_HOST}/live/stream/{sid}/index.m3u8"
    whep = cam.get("whep_url") or f"http://{RTSP_HOST}:8889/stream/{sid}/whep"
    return {"rtsp": rtsp, "hls": hls, "whep": whep}


def _coordinates(cam: dict) -> tuple[float | None, float | None, str, float | None]:
    """Accept only supplied, valid coordinates; never manufacture a map point."""
    try:
        lat, lng = float(cam["lat"]), float(cam["lng"])
    except (KeyError, TypeError, ValueError):
        return None, None, "unknown", None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        return None, None, "unknown", None
    try:
        confidence = float(cam.get("coord_confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return lat, lng, str(cam.get("coord_source") or "government_catalogue"), max(0.0, min(1.0, confidence))


def _department(name: str, location: str) -> tuple[str, float | None]:
    """Conservative source-name enrichment; it never replaces verified data."""
    value = f"{name} {location}".lower()
    rules = (("ahmedabad", "AMC / Gujarat Police"), ("junagadh", "Gujarat Police Junagadh"),
             ("rajkot", "Rajkot Police"), ("navsari", "Navsari Police"),
             ("gandhinagar", "Gujarat Police Gandhinagar"), ("patan", "Gujarat Police Patan"),
             ("gandhidham", "Gandhidham Police / Kutch"))
    for needle, department in rules:
        if needle in value:
            return department, 0.45
    # `department` is a required registry field.  Keep the unknown state
    # explicit instead of inserting NULL, while the source/confidence columns
    # make clear that this is not a verified attribution.
    return "Unassigned", None


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
    coordinate_counts = {}
    for cam in cameras:
        sid  = int(cam.get("id", 0))
        urls = _build_urls(cam)
        name = cam.get("location") or cam.get("name") or f"Camera {sid}"
        lat, lng, coord_source, coord_confidence = _coordinates(cam)
        department, department_confidence = _department(name, cam.get("location", ""))
        if lat is None:
            log.warning("Catalogue camera %s has no valid coordinates; retaining existing registry point if any", sid)
        else:
            coordinate_counts[(lat, lng)] = coordinate_counts.get((lat, lng), 0) + 1
        rows.append((
            sid,
            name,
            cam.get("location", ""),
            lat,
            lng,
            coord_source,
            coord_confidence,
            department,
            department_confidence,
            urls["rtsp"],
            urls["hls"],
            urls["whep"],
            # Catalogue metadata is configured data, not an observation.  A
            # missing value remains NULL so the UI can show N/A rather than a
            # fabricated default.
            str(cam["codec"]) if cam.get("codec") else None,
            int(cam["width"]) if cam.get("width") else None,
            int(cam["height"]) if cam.get("height") else None,
            float(cam["fps"]) if cam.get("fps") else None,
            "active" if cam.get("live", True) else "offline",
        ))

    for coordinates, count in coordinate_counts.items():
        if count > 1:
            log.warning("Catalogue has %s cameras at the same coordinates %s; verify source metadata", count, coordinates)

    sql = """
        INSERT INTO cameras
          (stream_id, name, location, lat, lng, coord_source, coord_confidence, department, department_confidence,
           rtsp_url, hls_url, whep_url,
           codec, width, height, fps, status, last_seen_at)
        VALUES %s
        ON CONFLICT (stream_id) DO UPDATE SET
          name         = EXCLUDED.name,
          location     = EXCLUDED.location,
          lat          = CASE WHEN EXCLUDED.lat IS NOT NULL AND COALESCE(cameras.coord_confidence, -1) <= COALESCE(EXCLUDED.coord_confidence, -1) THEN EXCLUDED.lat ELSE cameras.lat END,
          lng          = CASE WHEN EXCLUDED.lng IS NOT NULL AND COALESCE(cameras.coord_confidence, -1) <= COALESCE(EXCLUDED.coord_confidence, -1) THEN EXCLUDED.lng ELSE cameras.lng END,
          coord_source = CASE WHEN EXCLUDED.lat IS NOT NULL AND COALESCE(cameras.coord_confidence, -1) <= COALESCE(EXCLUDED.coord_confidence, -1) THEN EXCLUDED.coord_source ELSE cameras.coord_source END,
          coord_confidence = CASE WHEN EXCLUDED.lat IS NOT NULL AND COALESCE(cameras.coord_confidence, -1) <= COALESCE(EXCLUDED.coord_confidence, -1) THEN EXCLUDED.coord_confidence ELSE cameras.coord_confidence END,
          department = CASE WHEN cameras.department = 'Unassigned' OR (cameras.department_source NOT IN ('manual','government_seed','import') AND COALESCE(cameras.department_confidence, -1) <= COALESCE(EXCLUDED.department_confidence, -1)) THEN COALESCE(EXCLUDED.department, cameras.department) ELSE cameras.department END,
          department_source = CASE WHEN cameras.department = 'Unassigned' OR (cameras.department_source NOT IN ('manual','government_seed','import') AND COALESCE(cameras.department_confidence, -1) <= COALESCE(EXCLUDED.department_confidence, -1)) THEN CASE WHEN EXCLUDED.department IS NOT NULL THEN 'catalogue_inferred' ELSE cameras.department_source END ELSE cameras.department_source END,
          department_confidence = CASE WHEN cameras.department = 'Unassigned' OR (cameras.department_source NOT IN ('manual','government_seed','import') AND COALESCE(cameras.department_confidence, -1) <= COALESCE(EXCLUDED.department_confidence, -1)) THEN COALESCE(EXCLUDED.department_confidence, cameras.department_confidence) ELSE cameras.department_confidence END,
          rtsp_url     = EXCLUDED.rtsp_url,
          hls_url      = EXCLUDED.hls_url,
          whep_url     = EXCLUDED.whep_url,
          codec        = COALESCE(EXCLUDED.codec, cameras.codec),
          width        = COALESCE(EXCLUDED.width, cameras.width),
          height       = COALESCE(EXCLUDED.height, cameras.height),
          fps          = COALESCE(EXCLUDED.fps, cameras.fps),
          status       = EXCLUDED.status,
          last_seen_at = NOW()
    """
    template = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())"

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
