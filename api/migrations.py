"""Small, ordered SQL migration runner for the current Docker deployment."""
from pathlib import Path
import os
import re
import time

import psycopg2

_VERSION_RE = re.compile(r"^(\d+)_.*\.sql$")
MAX_CONNECT_ATTEMPTS = max(1, int(os.getenv("MIGRATION_CONNECT_ATTEMPTS", "12")))
CONNECT_RETRY_DELAY = max(0.25, float(os.getenv("MIGRATION_CONNECT_RETRY_DELAY", "2")))


def _connect_with_retry(database_url: str):
    last_error = None
    for attempt in range(1, MAX_CONNECT_ATTEMPTS + 1):
        try:
            return psycopg2.connect(database_url)
        except psycopg2.OperationalError as exc:
            last_error = exc
            if attempt == MAX_CONNECT_ATTEMPTS:
                raise
            time.sleep(CONNECT_RETRY_DELAY)
    raise last_error


def apply_migrations():
    database_url = os.getenv("DATABASE_URL", "")
    migration_dir = Path(os.getenv("MIGRATIONS_DIR", "/migrations"))
    if not migration_dir.exists():
        return
    paths = sorted(migration_dir.glob("*.sql"))
    seen = {}
    for path in paths:
        match = _VERSION_RE.match(path.name)
        if not match:
            raise RuntimeError(f"Migration filename must start with a numeric version: {path.name}")
        version = match.group(1)
        previous = seen.get(version)
        if previous:
            raise RuntimeError(f"Duplicate migration version {version}: {previous.name} and {path.name}")
        seen[version] = path

    conn = _connect_with_retry(database_url)
    try:
        with conn.cursor() as cur:
            # Multiple API workers can start together; serialize DDL and the
            # migration ledger with a transaction-scoped advisory lock.
            cur.execute("SELECT pg_advisory_xact_lock(8042601)")
            cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            for path in paths:
                cur.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (path.name,))
                if cur.fetchone():
                    continue
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (path.name,))
        conn.commit()
    finally:
        conn.close()
