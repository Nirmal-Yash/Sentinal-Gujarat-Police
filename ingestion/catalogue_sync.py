#!/usr/bin/env python3
"""Catalogue Sync — current cctv.corp8.cloud registry ingestion.

The current provider is a password-only web gateway which establishes a
session cookie; ingestion keeps that credential server-side and writes
canonical camera stream endpoints into the registry.
"""
import os
import time
import logging

import requests
import psycopg2
from psycopg2.extras import execute_values

log = logging.getLogger("catalogue_sync")
CCTV_BASE_URL = os.getenv("CCTV_BASE_URL", "https://cctv.corp8.cloud").rstrip("/")
CCTV_LOGIN_PATH = os.getenv("CCTV_LOGIN_PATH", "/auth/login")
CCTV_CATALOGUE_PATH = os.getenv("CCTV_CATALOGUE_PATH", "/cameras.json")
CCTV_PASSWORD = os.getenv("CCTV_PASSWORD", "")
RTSP_HOST_IP = os.getenv("RTSP_HOST_IP", "103.250.160.189")
RTSP_PORT = int(os.getenv("RTSP_PORT", "8554"))
DB_URL = os.getenv("DATABASE_URL", "")


def _canonical_id(raw_id) -> tuple[int, str]:
    text = str(raw_id or "").strip()
    if text.lower().startswith("cam"):
        text = text[3:]
    if not text.isdigit():
        raise ValueError(f"Invalid CCTV camera id: {raw_id!r}")
    numeric = int(text)
    if numeric < 0:
        raise ValueError(f"Invalid CCTV camera id: {raw_id!r}")
    return numeric, f"cam{numeric:02d}"


def _build_urls(cam: dict) -> dict:
    sid, canonical = _canonical_id(cam.get("id"))
    rtsp = cam.get("rtsp_url") or f"rtsp://{RTSP_HOST_IP}:{RTSP_PORT}/stream/{canonical}"
    hls = f"/api/cctv/{canonical}/index.m3u8"
    whep = cam.get("whep_url") or ""
    return {"stream_id": sid, "canonical_id": canonical, "rtsp": rtsp, "hls": hls, "whep": whep}


def _coordinates(cam: dict):
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


def _department(name: str, location: str):
    value = f"{name} {location}".lower()
    rules = (("ahmedabad", "AMC / Gujarat Police"), ("junagadh", "Gujarat Police Junagadh"), ("rajkot", "Rajkot Police"), ("navsari", "Navsari Police"), ("gandhinagar", "Gujarat Police Gandhinagar"), ("patan", "Gujarat Police Patan"), ("gandhidham", "Gandhidham Police / Kutch"))
    for needle, department in rules:
        if needle in value:
            return department, 0.45
    return "Unassigned", None


class CctvSession:
    """Password-only CCTV connector; no username/email is ever required."""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Sentinel-Ingestion/1.0",
            "Accept": "application/json, text/plain, */*",
        })
        self.access_token = None

    def login(self) -> None:
        if not CCTV_PASSWORD:
            raise RuntimeError("CCTV_PASSWORD is required for current CCTV catalogue access")
        response = self.session.post(
            f"{CCTV_BASE_URL}{CCTV_LOGIN_PATH}",
            data={"password": CCTV_PASSWORD},
            headers={"Referer": f"{CCTV_BASE_URL}/"},
            timeout=15,
            allow_redirects=True,
        )
        try:
            content_type = response.headers.get("Content-Type", "")
            payload = None
            if "json" in content_type.lower():
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
            if response.status_code not in {200, 204, 302, 303}:
                raise RuntimeError(f"CCTV login failed with HTTP {response.status_code}")
            if isinstance(payload, dict):
                for key in ("access_token", "token", "jwt"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        self.access_token = value.strip()
                        self.session.headers["Authorization"] = f"Bearer {self.access_token}"
                        break
            log.info(
                "CCTV login response: HTTP %s final_url=%s cookie=%s bearer=%s content_type=%s",
                response.status_code, response.url,
                bool(self.session.cookies.get_dict()),
                bool(self.access_token), content_type,
            )
        finally:
            response.close()

    def catalogue(self) -> list[dict]:
        self.login()
        response = self.session.get(
            f"{CCTV_BASE_URL}{CCTV_CATALOGUE_PATH}",
            timeout=15,
            allow_redirects=False,
        )
        try:
            if response.status_code in {401, 403, 302, 303}:
                response.close()
                self.login()
                response = self.session.get(
                    f"{CCTV_BASE_URL}{CCTV_CATALOGUE_PATH}",
                    timeout=15,
                    allow_redirects=False,
                )
            if response.status_code in {401, 403, 302, 303}:
                raise RuntimeError(
                    f"CCTV catalogue authentication rejected (HTTP {response.status_code})"
                )
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError("CCTV catalogue did not return valid JSON") from exc
            if isinstance(payload, dict):
                payload = payload.get("cameras") or payload.get("streams") or payload.get("data")
            if not isinstance(payload, list):
                raise RuntimeError("CCTV catalogue is not a JSON array")
            cameras = [item for item in payload if isinstance(item, dict)]
            if not cameras:
                raise RuntimeError("CCTV catalogue returned no camera records")
            return cameras
        finally:
            response.close()


def fetch_catalogue(retries: int = 5):
    delay = 2
    for attempt in range(retries):
        try:
            cameras = CctvSession().catalogue()
            log.info("CCTV catalogue authenticated successfully: %s camera records", len(cameras))
            return cameras
        except Exception as exc:
            log.warning("CCTV catalogue fetch attempt %s/%s failed: %s", attempt + 1, retries, exc)
            if attempt + 1 < retries:
                time.sleep(delay)
                delay = min(delay * 2, 30)
    return []


def sync(conn=None) -> int:
    cameras = fetch_catalogue()
    if not cameras:
        log.warning("Empty CCTV catalogue — skipping sync")
        return 0
    close_after = conn is None
    conn = conn or psycopg2.connect(DB_URL)
    rows = []
    coordinate_counts = {}
    seen_stream_ids = set()
    for cam in cameras:
        urls = _build_urls(cam)
        sid = urls["stream_id"]
        if sid in seen_stream_ids:
            raise RuntimeError(f"Duplicate stream_id in CCTV catalogue: {sid}")
        seen_stream_ids.add(sid)
        name = cam.get("location") or cam.get("name") or f"Camera {sid}"
        lat, lng, coord_source, coord_confidence = _coordinates(cam)
        department, department_confidence = _department(name, cam.get("location", ""))
        provided_codec = str(cam["codec"]) if cam.get("codec") is not None else None
        provided_width = int(cam["width"]) if cam.get("width") is not None else None
        provided_height = int(cam["height"]) if cam.get("height") is not None else None
        provided_fps = float(cam["fps"]) if cam.get("fps") is not None else None
        if lat is not None:
            coordinate_counts[(lat, lng)] = coordinate_counts.get((lat, lng), 0) + 1
        rows.append((sid, name, cam.get("location", ""), lat, lng, coord_source, coord_confidence, department, department_confidence, urls["rtsp"], urls["hls"], urls["whep"], provided_codec, provided_width, provided_height, provided_fps, provided_codec, provided_width, provided_height, provided_fps, "active" if cam.get("live", True) else "offline", "cctv.corp8.cloud", urls["canonical_id"]))
    for coordinates, count in coordinate_counts.items():
        if count > 1:
            log.warning("CCTV catalogue has %s cameras at same coordinates %s", count, coordinates)
    sql = """
        INSERT INTO cameras
          (stream_id,name,location,lat,lng,coord_source,coord_confidence,
           department,department_confidence,rtsp_url,hls_url,whep_url,
           codec,width,height,fps,provided_codec,provided_width,provided_height,
           provided_fps,status,last_seen_at,source_system,external_id)
        VALUES %s
        ON CONFLICT (stream_id) DO UPDATE SET
          name=EXCLUDED.name, location=EXCLUDED.location,
          lat=CASE WHEN EXCLUDED.lat IS NOT NULL AND COALESCE(cameras.coord_confidence,-1) <= COALESCE(EXCLUDED.coord_confidence,-1) THEN EXCLUDED.lat ELSE cameras.lat END,
          lng=CASE WHEN EXCLUDED.lng IS NOT NULL AND COALESCE(cameras.coord_confidence,-1) <= COALESCE(EXCLUDED.coord_confidence,-1) THEN EXCLUDED.lng ELSE cameras.lng END,
          coord_source=CASE WHEN EXCLUDED.lat IS NOT NULL AND COALESCE(cameras.coord_confidence,-1) <= COALESCE(EXCLUDED.coord_confidence,-1) THEN EXCLUDED.coord_source ELSE cameras.coord_source END,
          coord_confidence=CASE WHEN EXCLUDED.lat IS NOT NULL AND COALESCE(cameras.coord_confidence,-1) <= COALESCE(EXCLUDED.coord_confidence,-1) THEN EXCLUDED.coord_confidence ELSE cameras.coord_confidence END,
          department=CASE WHEN cameras.department='Unassigned' OR (cameras.department_source NOT IN ('manual','government_seed','import') AND COALESCE(cameras.department_confidence,-1) <= COALESCE(EXCLUDED.department_confidence,-1)) THEN COALESCE(EXCLUDED.department,cameras.department) ELSE cameras.department END,
          department_source=CASE WHEN cameras.department='Unassigned' OR (cameras.department_source NOT IN ('manual','government_seed','import') AND COALESCE(cameras.department_confidence,-1) <= COALESCE(EXCLUDED.department_confidence,-1)) THEN CASE WHEN EXCLUDED.department IS NOT NULL THEN 'catalogue_inferred' ELSE cameras.department_source END ELSE cameras.department_source END,
          department_confidence=CASE WHEN cameras.department='Unassigned' OR (cameras.department_source NOT IN ('manual','government_seed','import') AND COALESCE(cameras.department_confidence,-1) <= COALESCE(EXCLUDED.department_confidence,-1)) THEN COALESCE(EXCLUDED.department_confidence,cameras.department_confidence) ELSE cameras.department_confidence END,
          rtsp_url=EXCLUDED.rtsp_url, hls_url=EXCLUDED.hls_url, whep_url=EXCLUDED.whep_url,
          source_system=EXCLUDED.source_system, external_id=EXCLUDED.external_id,
          provided_codec=EXCLUDED.provided_codec, provided_width=EXCLUDED.provided_width,
          provided_height=EXCLUDED.provided_height, provided_fps=EXCLUDED.provided_fps,
          codec=COALESCE(EXCLUDED.codec,cameras.codec), width=COALESCE(EXCLUDED.width,cameras.width),
          height=COALESCE(EXCLUDED.height,cameras.height), fps=COALESCE(EXCLUDED.fps,cameras.fps),
          status=EXCLUDED.status, last_seen_at=NOW(), updated_at=NOW()
    """
    template = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s)"
    expected_values = 23
    if rows and len(rows[0]) != expected_values:
        raise RuntimeError(f"Catalogue row/template mismatch: row has {len(rows[0])} values; expected {expected_values}")
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, template=template)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if close_after:
            conn.close()
    log.info("CCTV catalogue sync: %s cameras upserted", len(rows))
    return len(rows)


def run_loop():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [CATALOGUE][%(levelname)s] %(message)s")
    for _ in range(20):
        try:
            psycopg2.connect(DB_URL).close()
            break
        except Exception as exc:
            log.info("Waiting for DB: %s", exc)
            time.sleep(3)
    while True:
        try:
            sync()
        except Exception as exc:
            log.error("CCTV catalogue sync error: %s", exc, exc_info=True)
        time.sleep(max(30, int(os.getenv("CATALOGUE_SYNC_INTERVAL", "300"))))


if __name__ == "__main__":
    run_loop()
