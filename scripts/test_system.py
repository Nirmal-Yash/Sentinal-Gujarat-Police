#!/usr/bin/env python3
"""Sentinel AI - local Docker Compose health check."""
import json
import os
import sys
import urllib.request

API = "http://localhost:8000"
CHECKS_PASSED = 0
CHECKS_TOTAL = 0


def check(label, ok, detail=""):
    global CHECKS_PASSED, CHECKS_TOTAL
    CHECKS_TOTAL += 1
    print(f"  {'[OK]' if ok else '[FAIL]'}  {label}" + (f" -> {detail}" if detail else ""))
    if ok:
        CHECKS_PASSED += 1
    return ok


def get(path, timeout=5):
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as response:
            return json.loads(response.read())
    except Exception:
        return None


def is_available(path, timeout=5):
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def check_redis():
    try:
        import redis
        client = redis.from_url("redis://localhost:6379")
        client.ping()
        check("Redis ping", True)
        check("raw_frames stream", client.xlen("raw_frames") >= 0, f"{client.xlen('raw_frames')} messages")
        check("detections stream", client.xlen("detections") >= 0, f"{client.xlen('detections')} messages")
        check("alerts stream", client.xlen("alerts") >= 0, f"{client.xlen('alerts')} messages")
    except ImportError:
        print("  [SKIP] redis-py not installed locally - skipping Redis checks")
    except Exception as exc:
        check("Redis ping", False, str(exc))


def check_postgres():
    try:
        import psycopg2
        password = os.getenv("POSTGRES_PASSWORD", "change-me")
        conn = psycopg2.connect(f"postgresql://sentinel:{password}@localhost:5432/sentinel")
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM cameras"); cameras = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM watchlist WHERE is_active"); watchlist = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM alerts"); alerts = cur.fetchone()[0]
        conn.close()
        check("PostgreSQL connection", True)
        check("Cameras seeded", cameras > 0, f"{cameras} cameras")
        check("Watchlist entries", watchlist >= 0, f"{watchlist} active")
        check("Alerts table accessible", True, f"{alerts} alerts total")
    except ImportError:
        print("  [SKIP] psycopg2 not installed locally - skipping DB checks")
    except Exception as exc:
        check("PostgreSQL connection", False, str(exc))


def check_api():
    health = get("/health")
    check("API health endpoint", health is not None and health.get("status") == "ok")
    cameras = get("/cameras/")
    check("GET /cameras/", isinstance(cameras, list), f"{len(cameras) if cameras else 0} cameras")
    check("GET /alerts/", isinstance(get("/alerts/"), list))
    watchlist = get("/watchlist/")
    check("GET /watchlist/", isinstance(watchlist, list), f"{len(watchlist) if watchlist else 0} entries")
    check("GET /alerts/stats/counts", get("/alerts/stats/counts") is not None)
    check("Swagger docs accessible", is_available("/docs"))


def main():
    print("\n--- Sentinel AI - System Health Check ---\n")
    print("[ Redis ]"); check_redis()
    print("\n[ PostgreSQL ]"); check_postgres()
    print("\n[ FastAPI ]"); check_api()
    print(f"\n--- {CHECKS_PASSED}/{CHECKS_TOTAL} checks passed ---\n")
    if CHECKS_PASSED < CHECKS_TOTAL:
        sys.exit(1)


if __name__ == "__main__":
    main()
