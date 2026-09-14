"""Idempotently seed one RBAC account from explicit environment secrets only."""
import os, sys
import bcrypt, psycopg2

username = os.getenv("SENTINEL_ADMIN_USERNAME")
password = os.getenv("SENTINEL_ADMIN_PASSWORD")
role = os.getenv("SENTINEL_ADMIN_ROLE", "SUPERADMIN").upper()
db_url = os.getenv("DATABASE_URL", "postgresql://sentinel:sentinelpass@localhost:5432/sentinel")
if not username or not password:
    sys.exit("Set SENTINEL_ADMIN_USERNAME and SENTINEL_ADMIN_PASSWORD; no default credentials exist.")
if role not in {"SUPERADMIN", "ADMIN", "OPERATOR", "VIEWER"}:
    sys.exit("SENTINEL_ADMIN_ROLE is invalid")
digest = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
    cur.execute("""INSERT INTO users(username,password_hash,role) VALUES(%s,%s,%s)
        ON CONFLICT(username) DO UPDATE SET password_hash=EXCLUDED.password_hash, role=EXCLUDED.role, is_active=TRUE""", (username, digest, role))
print(f"Seeded {role} account for {username}.")
