#!/usr/bin/env python3
"""Seed a curated Test Mode demo session for GJ01AB1234 GIS route walkthrough."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.getenv("SENTINEL_API_URL", "http://localhost:8000").rstrip("/")
USER = os.getenv("SENTINEL_ADMIN_USERNAME") or os.getenv("BOOTSTRAP_ADMIN_USERNAME")
PASSWORD = os.getenv("SENTINEL_ADMIN_PASSWORD") or os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
DEMO_SESSION_NAME = os.getenv("DEMO_SESSION_NAME", "Evaluator Demo Session")
ROUTE_CONFIG = Path(__file__).resolve().parent / "config" / "test_vehicle_route.json"
if not ROUTE_CONFIG.is_file():
    ROUTE_CONFIG = Path(__file__).resolve().parent.parent / "config" / "test_vehicle_route.json"


def login():
    if not USER or not PASSWORD:
        sys.exit("Set SENTINEL_ADMIN_USERNAME and SENTINEL_ADMIN_PASSWORD (or BOOTSTRAP_* equivalents).")
    req = urllib.request.Request(
        f"{API}/api/v1/auth/login",
        data=json.dumps({"username": USER, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["access_token"]


def api(method, path, token, data=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(f"{API}{path}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def load_route_config():
    if not ROUTE_CONFIG.exists():
        return {"demo_plate": "GJ01AB1234", "feeds": []}
    with ROUTE_CONFIG.open(encoding="utf-8") as fh:
        return json.load(fh)


def match_asset(assets, asset_match):
    needle = str(asset_match or "").lower()
    for asset in assets:
        hay = f"{asset.get('display_name', '')} {asset.get('id', '')}".lower()
        if needle and needle in hay:
            return asset
    return None


def main():
    print("=== SEED DEMO TEST SESSION (GJ01AB1234) ===")
    token = login()
    route = load_route_config()
    demo_plate = route.get("demo_plate") or "GJ01AB1234"

    try:
        active = api("GET", "/api/v1/test/sessions/active", token)
        if active and active.get("id"):
            print(f"Closing existing session {active['id']}...")
            api("DELETE", f"/api/v1/test/sessions/{active['id']}", token)
    except urllib.error.HTTPError:
        pass

    assets = api("GET", "/api/v1/test/assets", token)
    if not assets:
        print("No test video assets found. Ensure /videos is mounted and TEST_ENDPOINT_ENABLED=true.")
        return 1

    cameras = []
    for feed in route.get("feeds") or []:
        asset = match_asset(assets, feed.get("asset_match"))
        if not asset:
            print(f"Warning: no asset matched '{feed.get('asset_match')}' — skipping feed.")
            continue
        cameras.append({
            "asset_id": asset["id"],
            "camera_label": feed.get("camera_label") or asset.get("display_name") or "Demo Camera",
            "loop": True,
        })

    if not cameras:
        print("No route feeds matched uploaded assets. Falling back to first available assets.")
        cameras = [
            {"asset_id": asset["id"], "camera_label": f"Demo Camera {index + 1}", "loop": True}
            for index, asset in enumerate(assets[:3])
        ]

    session = api("POST", "/api/v1/test/sessions", token, {"name": DEMO_SESSION_NAME, "cameras": cameras})
    session_id = session["id"]
    print(f"Created session: {session_id}")

    seeded = api("POST", f"/api/v1/test/sessions/{session_id}/seed-demo-route", token)
    print(f"Seeded demo route for {seeded.get('plate')}: {seeded.get('sightings_seeded')} sightings")

    feeds = api("GET", f"/api/v1/test/sessions/{session_id}/cameras", token)
    print(f"Attached feeds: {len(feeds)}")
    for feed in feeds:
        print(f"  stream {feed.get('stream_id')}: {feed.get('name')} @ {feed.get('location')} ({feed.get('lat')}, {feed.get('lng')})")

    print("\nDemo session ready.")
    print(f"  Session ID: {session_id}")
    print(f"  Investigate {demo_plate} → Show Full Route on Map")
    return 0


if __name__ == "__main__":
    sys.exit(main())
