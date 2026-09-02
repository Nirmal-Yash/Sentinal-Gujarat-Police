# 🛡️ Sentinel AI — Gujarat Police Innovation Challenge 2026

AI-powered unified CCTV surveillance platform.

## Docker Quick Start

Prerequisites: Docker Desktop/Engine with Compose, 8 GB RAM minimum (16 GB recommended), and adequate free disk space.

### Create the environment file

Linux/macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### Required Compose variables

`docker-compose.yml` requires `POSTGRES_PASSWORD` and `SECRET_KEY`. If either is missing, Docker Compose fails during variable interpolation before any service starts. Typical error:

```text
required variable POSTGRES_PASSWORD is missing a value: POSTGRES_PASSWORD must be supplied
```

For local/demo use, set at least:

```dotenv
POSTGRES_PASSWORD=change-me
SECRET_KEY=change-me
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=change-me
BOOTSTRAP_ADMIN_ROLE=SUPERADMIN
```

Use strong, non-default values outside local development.

### Validate and start

```bash
docker compose config -q
docker compose up -d --build
```

On PowerShell the same commands work unchanged.

### If the error still appears

Check what Compose receives:

```powershell
docker compose config | Select-String "POSTGRES_PASSWORD|SECRET_KEY"
```

If `POSTGRES_PASSWORD` is absent, verify that `.env` exists in the same directory as `docker-compose.yml` and contains a non-empty value. Do not rely on setting the variable only in another terminal/session.

Important: a persistent PostgreSQL volume keeps the existing database role password. Changing `POSTGRES_PASSWORD` in `.env` does **not** change the password of an already-initialized PostgreSQL role. If the API later reports `password authentication failed for user "sentinel"`, update the existing role password from a privileged PostgreSQL session, or recreate the local database volume only when deleting its data is acceptable.

Do not run `docker compose down` or `docker compose build` expecting either command to bypass missing required environment variables: Compose interpolates the file before executing the requested operation.

Dashboard: http://localhost:3000
API docs: http://localhost:8000/docs

## Architecture

```text
Camera / Test Video
      ↓
Ingestion
      ↓
Redis Streams
      ↓
YOLOv8 + DeepSORT + ANPR/OCR + InsightFace
      ↓
Intelligence / Watchlist / Alerts
      ↓
FastAPI + WebSocket + React + Leaflet
      ↕
PostgreSQL + PostGIS + pgvector + Redis
```

The system intentionally remains modular and Docker-based; larger deployments can introduce GPU inference, distributed event infrastructure, object storage and regional/edge processing when measured scale requirements justify them.

## Services

| Service | Port | Purpose |
|---|---:|---|
| redis | 6379 | Message bus/cache |
| postgres | 5432 | Registry, events, alerts, watchlist, tracks |
| mediamtx | 8554 | Test/camera media gateway |
| ingestion | — | Frame ingestion |
| ai_worker | — | Detection, tracking, ANPR and analytics |
| person_investigation | — | On-demand face investigation |
| intelligence | — | Watchlist, correlation and alerts |
| api | 8000 | REST API + WebSocket |
| dashboard | 3000 | React operator UI |

## Core Workflows

- Monitor: heterogeneous camera feeds with buffering and fallback handling.
- GIS: Gujarat-first camera map, clustering, alerts and vehicle journeys.
- Investigate: submit-driven plate investigation and photo-based person investigation.
- Watchlist: background plate/face matching with lifecycle alerts.
- Test Mode: isolated video sessions, detections, sightings, alerts, search and exports.
- Camera Registry: manual onboarding, bulk CSV/XLSX import, vendor/model validation and GIS location.
- Authentication/RBAC: JWT/WebSocket authorization with VIEWER, OPERATOR, INVESTIGATOR, AUDITOR, ADMIN and SUPERADMIN roles.

## Development / Diagnostics

```bash
docker compose logs -f api
docker compose logs -f ai_worker
docker compose logs -f intelligence
python scripts/test_system.py
```

For Test Mode, use the Dashboard → Test Mode workflow. Test data is kept isolated from production camera data.

## Important Environment Notes

See `.env.example` for the full configuration surface, including ANPR tuning, feed reconnect settings, Test Mode, RBAC bootstrap and evidence limits.

Never commit `.env` or real credentials to the repository.
