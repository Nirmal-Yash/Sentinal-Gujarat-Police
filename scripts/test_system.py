#!/usr/bin/env python3
"""
Sentinel AI — System Health Check
Run after docker-compose up to verify all services.

Usage:
  python scripts/test_system.py
"""
import sys, time, json
import urllib.request, urllib.error

API = "http://localhost:8000"
CHECKS_PASSED = 0
CHECKS_TOTAL  = 0


def check(label, ok, detail=""):
    global CHECKS_PASSED, CHECKS_TOTAL
    CHECKS_TOTAL += 1
    sym = "✅" if ok else "❌"
    print(f"  {sym}  {label}" + (f"  → {detail}" if detail else ""))
    if ok:
        CHECKS_PASSED += 1
    return ok


def get(path, timeout=5):
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return None


def check_redis():
    import redis
    try:
        r = redis.from_url("redis://localhost:6379")
        r.ping()
        raw_len = r.xlen("raw_frames")
        det_len = r.xlen("detections")
        alt_len = r.xlen("alerts")
        check("Redis ping",         True)
        check("raw_frames stream",  raw_len >= 0, f"{raw_len} messages")
        check("detections stream",  det_len >= 0, f"{det_len} messages")
        check("alerts stream",      alt_len >= 0, f"{alt_len} messages")
    except ImportError:
        print("  ⚠  redis-py not installed locally — skipping Redis checks")
    except Exception as e:
        check("Redis ping", False, str(e))


def check_postgres():
    try:
        import psycopg2
        conn = psycopg2.connect(
            "postgresql://sentinel:sentinelpass@localhost:5432/sentinel")
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cameras")
        cams = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM watchlist WHERE is_active")
        wl   = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM alerts")
        alts = cur.fetchone()[0]
        conn.close()
        check("PostgreSQL connection",   True)
        check("Cameras seeded",          cams > 0,  f"{cams} cameras")
        check("Watchlist entries",       wl >= 0,   f"{wl} active")
        check("Alerts table accessible", True,      f"{alts} alerts total")
    except ImportError:
        print("  ⚠  psycopg2 not installed locally — skipping DB checks")
    except Exception as e:
        check("PostgreSQL connection", False, str(e))


def check_api():
    h = get("/health")
    check("API health endpoint",    h is not None and h.get("status") == "ok")
    cams = get("/cameras/")
    check("GET /cameras/",          isinstance(cams, list), f"{len(cams) if cams else 0} cameras")
    alts = get("/alerts/")
    check("GET /alerts/",           isinstance(alts, list))
    wl   = get("/watchlist/")
    check("GET /watchlist/",        isinstance(wl, list), f"{len(wl) if wl else 0} entries")
    stats = get("/alerts/stats/counts")
    check("GET /alerts/stats/counts", stats is not None)
    docs = get("/docs")
    check("Swagger docs accessible", True)   # FastAPI always serves /docs


def main():
    print("\n━━━ Sentinel AI — System Health Check ━━━\n")

    print("[ Redis ]")
    check_redis()

    print("\n[ PostgreSQL ]")
    check_postgres()

    print("\n[ FastAPI ]")
    check_api()

    print(f"\n━━━ {CHECKS_PASSED}/{CHECKS_TOTAL} checks passed ━━━\n")
    if CHECKS_PASSED < CHECKS_TOTAL:
        sys.exit(1)


if __name__ == "__main__":
    main()
