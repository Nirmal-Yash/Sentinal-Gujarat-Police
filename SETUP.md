# Sentinel AI — Complete Setup Guide (Windows 11, Starting From Zero)

## What you already have ✓
- Windows 11
- Docker Desktop installed
- Git installed

---

## Step 0 — Verify Docker Desktop is ready

Open **Docker Desktop** from the Start menu and wait until the Linux engine is running.

Then open **PowerShell** and run:
```powershell
docker --version
docker compose version
```

### Memory allocation (important — 16 GB machine)
Docker Desktop should be given enough RAM for the AI models.

1. Docker Desktop → Settings → Resources → Advanced
2. Set Memory to about 10 GB
3. Set CPUs to about 6
4. Apply & Restart

---

## Step 1 — Get the project

```powershell
cd C:\path\to\sentinel-ai
git pull origin main
```

---

## Step 2 — Configure environment

```powershell
copy .env.example .env
```

Set the assigned CCTV password in `.env`:
```text
CCTV_PASSWORD=replace-with-assigned-feed-password
```

Current CCTV infrastructure:
```text
CCTV_BASE_URL=https://cctv.corp8.cloud
CCTV_LOGIN_PATH=/auth/login
CCTV_CATALOGUE_PATH=/cameras.json
RTSP_HOST_IP=103.250.160.189
RTSP_PORT=8554
```

Database for Docker:
```text
DATABASE_URL=postgresql://sentinel:sentinel@postgres:5432/sentinel
```

Use a long random local value for:
```text
SECRET_KEY=<long-random-secret>
```

Do not commit `.env`.

---

## Step 3 — Build

```powershell
docker compose config -q
docker compose build
```

---

## Step 4 — Start

```powershell
docker compose up -d
```

Check:
```powershell
docker compose ps
```

Expected core services:
```text
postgres
redis
mediamtx
api
ingestion
ai_worker
intelligence
dashboard
```

---

## Step 5 — Expected feed flow

The production source of truth is the authenticated CCTV gateway:

```text
https://cctv.corp8.cloud/auth/login
        ↓
https://cctv.corp8.cloud/cameras.json
        ↓
cam01 ... cam30
        ↓
RTSP rtsp://103.250.160.189:8554/stream/camNN
        ↓
ingestion
        ↓
Redis raw_frames
        ↓
ai_worker
        ↓
YOLO / ANPR
```

The retired `live.corp8.cloud` infrastructure is not part of the current runtime.

---

## Step 6 — Open dashboard

```text
http://localhost:3000
```

API:
```text
http://localhost:8000/docs
```

---

## Step 7 — Verify pipeline

```powershell
docker compose logs --tail=150 ingestion
docker compose logs --tail=100 ai_worker
```

Redis:
```powershell
docker compose exec redis redis-cli XLEN raw_frames
docker compose exec redis redis-cli XLEN detections
docker compose exec redis redis-cli XLEN anpr_requests
docker compose exec redis redis-cli XLEN alerts
```

Camera runtime telemetry:
```powershell
docker compose exec postgres psql -U sentinel -d sentinel -c "SELECT stream_id,name,health_status,connectivity_status,last_frame_at,observed_decode_fps,observed_published_fps,reconnect_count,decode_failure_count FROM cameras ORDER BY stream_id;"
```

---

## Step 8 — Browser playback diagnostics

Open:
```text
F12 → Network → m3u8
```

Healthy playback should show an application-local request similar to:
```text
/api/cctv/cam01/index.m3u8?access_token=...
```

Expected:
```text
HTTP 200
Response begins #EXTM3U
```

The browser must never receive the CCTV provider password.

---

## Step 9 — Run local regression checks

```powershell
python scripts/test_system.py
node scripts/p0_browser_regression.mjs
python scripts/validate_refactor.py
docker compose config -q
```

---

## Troubleshooting

**Camera grid shows Connecting…**
```powershell
docker compose logs --tail=250 ingestion
```

**No frames**
```powershell
docker compose exec redis redis-cli XLEN raw_frames
```

**ANPR not dispatching**
```powershell
docker compose exec redis redis-cli XREVRANGE anpr_requests + - COUNT 10
docker compose logs --tail=250 ai_worker
```

**H.264 reconnects**
```powershell
docker compose logs --since=30m ingestion | Select-String -Pattern "error while decoding MB|frame-read failures|reconnecting|reconnected"
```

**Database connectivity**
```powershell
Test-NetConnection localhost -Port 5432
```

**Docker engine/image problems**
```powershell
docker info
docker compose ps
```

---

## Production-oriented acceptance checklist

- [ ] CCTV password authentication succeeds
- [ ] 30-camera catalogue sync succeeds
- [ ] `cam01...cam30` identities are present
- [ ] RTSP/TCP workers connect
- [ ] `raw_frames` receives frames
- [ ] YOLO detections are produced
- [ ] ANPR requests are produced
- [ ] HLS playback returns `#EXTM3U`
- [ ] Browser does not receive CCTV password
- [ ] `last_frame_at` is populated and advances
- [ ] reconnects recover without permanent worker death
- [ ] no runtime dependency on retired `live.corp8.cloud`
- [ ] local validation scripts pass
- [ ] all required CI gates pass on GitHub Actions
