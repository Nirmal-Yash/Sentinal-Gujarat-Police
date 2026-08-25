"""Small, ordered SQL migration runner for the current Docker deployment."""
from pathlib import Path
import os
import psycopg2


def apply_migrations():
    database_url = os.getenv("DATABASE_URL", "")
    migration_dir = Path(os.getenv("MIGRATIONS_DIR", "/migrations"))
    if not migration_dir.exists():
        return
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            # Multiple API workers can start together; serialize DDL and the
            # migration ledger with a transaction-scoped advisory lock.
            cur.execute("SELECT pg_advisory_xact_lock(8042601)")
            cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            for path in sorted(migration_dir.glob("*.sql")):
                cur.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (path.name,))
                if cur.fetchone():
                    continue
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (path.name,))
        conn.commit()
    finally:
        conn.close()
