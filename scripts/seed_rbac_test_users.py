#!/usr/bin/env python3
"""Create one isolated test account for every Sentinel RBAC role.

Usage:
  DATABASE_URL=postgresql://... python scripts/seed_rbac_test_users.py

The script is idempotent. It never stores plaintext passwords in the repository.
Set RBAC_TEST_PASSWORD to use one known password for every test account; otherwise
an independent random password is generated and printed once for the operator.
"""
from __future__ import annotations

import os
import secrets
import string
import sys

import bcrypt
import psycopg2

ROLES = ("SUPERADMIN", "ADMIN", "OPERATOR", "INVESTIGATOR", "VIEWER", "AUDITOR")
PREFIX = os.getenv("RBAC_TEST_USERNAME_PREFIX", "rbac-test")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sentinel:sentinelpass@localhost:5432/sentinel")
SHARED_PASSWORD = os.getenv("RBAC_TEST_PASSWORD", "").strip()


def password_for(role: str) -> str:
    if SHARED_PASSWORD:
        return SHARED_PASSWORD
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*_-"
    return "RBAC-" + role.lower() + "-" + "".join(secrets.choice(alphabet) for _ in range(20))


def main() -> int:
    accounts = []
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        for role in ROLES:
            username = f"{PREFIX}-{role.lower()}"
            password = password_for(role)
            digest = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            cur.execute(
                """INSERT INTO users(username,password_hash,role,is_active)
                   VALUES(%s,%s,%s,TRUE)
                   ON CONFLICT(username) DO UPDATE SET
                     password_hash=EXCLUDED.password_hash,
                     role=EXCLUDED.role,
                     is_active=TRUE""",
                (username, digest, role),
            )
            accounts.append((username, role, password))

    print("RBAC test accounts created/updated:")
    print("username | role | password")
    print("---------|------|---------")
    for username, role, password in accounts:
        print(f"{username} | {role} | {password}")
    print("\nThese are test-only accounts. Do not reuse the generated credentials outside the test environment.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except psycopg2.Error as exc:
        print(f"RBAC seed failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
