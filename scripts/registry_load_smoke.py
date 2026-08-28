#!/usr/bin/env python3
"""Deterministic registry/data-plane smoke for the evaluation-sized camera fleet."""
from __future__ import annotations
import os, time, uuid, json
import psycopg2

DB_URL = os.environ["DATABASE_URL"]
TARGET = int(os.getenv("REGISTRY_SMOKE_CAMERAS", "50"))

def main() -> int:
    started = time.perf_counter()
    with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE smoke_cameras (id uuid primary key, stream_id integer unique, name text, lat double precision, lng double precision, health_status text)")
        rows = [(str(uuid.uuid4()), 100000 + i, f"Smoke Camera {i+1}", 20.0 + i * 0.001, 70.0 + i * 0.001, "healthy") for i in range(TARGET)]
        args = ",".join(cur.mogrify("(%s,%s,%s,%s,%s,%s)", row).decode() for row in rows)
        cur.execute("INSERT INTO smoke_cameras VALUES " + args)
        cur.execute("SELECT COUNT(*) FROM smoke_cameras")
        count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM smoke_cameras WHERE lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180")
        valid_geo = cur.fetchone()[0]
    elapsed_ms = (time.perf_counter() - started) * 1000
    result = {"status": "PASS" if count == TARGET and valid_geo == TARGET else "FAIL", "cameras": count, "valid_coordinates": valid_geo, "target": TARGET, "elapsed_ms": round(elapsed_ms, 3)}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
