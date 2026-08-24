#!/usr/bin/env python3
"""
Seed the watchlist with demo face embeddings (random unit vectors).
In production, replace with real face images processed through InsightFace.

Usage:
  docker-compose exec intelligence python /app/seed_watchlist.py
  OR:
  python seed_watchlist.py
"""
import os, sys, struct, base64
import numpy as np
import psycopg2

DB_URL = os.getenv("DATABASE_URL",
    "postgresql://sentinel:sentinelpass@localhost:5432/sentinel")


def random_unit_embedding(dim=512, seed=None):
    rng = np.random.default_rng(seed)
    v   = rng.normal(size=dim).astype(np.float32)
    return v / np.linalg.norm(v)


def emb_to_pg_vector(v: np.ndarray) -> str:
    """Convert numpy float32 array to pgvector literal string."""
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def main():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    suspects = [
        ("Suspect Alpha", "person", "Seen near market twice",     None,           1),
        ("Suspect Beta",  "person", "Highway checkpoint incident", None,           2),
        ("GJ03AA1234",    "vehicle","Reported stolen car",        "GJ03AA1234",   None),
        ("GJ01BB5678",    "vehicle","Robbery connection",         "GJ01BB5678",   None),
    ]

    for name, etype, desc, plate, seed in suspects:
        emb  = random_unit_embedding(seed=seed) if seed else None
        vec  = emb_to_pg_vector(emb) if emb is not None else None

        cur.execute("""
            UPDATE watchlist
            SET embedding = %s::vector
            WHERE name = %s AND embedding IS NULL
        """, (vec, name))
        if cur.rowcount == 0:
            cur.execute("""
                INSERT INTO watchlist (name, entity_type, description, plate_number, embedding, alert_priority)
                VALUES (%s, %s, %s, %s, %s::vector, 'HIGH')
                ON CONFLICT DO NOTHING
            """, (name, etype, desc, plate, vec))
        print(f"  Seeded: {name}")

    conn.commit()
    cur.close()
    conn.close()
    print("Watchlist seeding complete.")


if __name__ == "__main__":
    main()
