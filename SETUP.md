# Sentinel AI — Complete Setup Guide (Windows 11, Starting From Zero)

## What you already have ✓
- Windows 11
- Docker Desktop installed
- Git installed

---

## Step 0 — Verify Docker Desktop is ready

Open **Docker Desktop** from the Start menu.  
Wait until the bottom-left shows a green whale icon that says **"Engine running"**.

Then open **PowerShell** (search "PowerShell" in Start) and run:
```powershell
docker --version
docker compose version
```
Both should return version numbers. If not, restart Docker Desktop and try again.

### Memory allocation (important — 16 GB machine)
Docker Desktop must be given enough RAM for the AI models.

1. Click the **gear icon** (⚙️) in Docker Desktop top-right
2. Go to **Resources → Advanced**
3. Set **Memory** to **10 GB** (leave 6 GB for Windows)
4. Set **CPUs** to **6** (you likely have 8 logical cores)
5. Click **Apply & Restart**

---

## Step 1 — Get the project

Download and unzip `sentinel-ai.zip` into a folder, then open PowerShell there:
```powershell
cd C:\path\to\sentinel-ai
```

Or if you received it as a Git repo:
```powershell
git clone <repo-url>
cd sentinel-ai
```

---

## Step 2 — Configure environment

```powershell
copy .env.example .env
```

Open `.env` in Notepad (or VS Code) — the defaults are correct for the live feeds.  
**No changes needed** unless you have custom credentials.

Key values already set:
```
RTSP_HOST=live.corp8.cloud
INGEST_API=http://live.corp8.cloud/api/ingest
FRAME_FPS=3
FRAME_SKIP=3
YOLO_WORKERS=4
```
> **YOLO_WORKERS=4** means 4 parallel detection processes sharing your CPU cores.  
> **FRAME_SKIP=3** means 1 detection per second per camera (3 FPS ÷ 3 = 1 Hz).  
> This is tuned for your Intel Iris CPU with 30 live cameras.

---

## Step 3 — First build (downloads AI models — ~4 GB, takes 10–20 min)

```powershell
docker compose build
```

This will:
- Download Python, Redis, PostgreSQL images
- Download YOLOv8n weights from Ultralytics
- Download EasyOCR English model
- Build the React dashboard

You will see download progress. This only happens once — subsequent starts are instant.

---

## Step 4 — Start the system

```powershell
docker compose up
```

Watch the logs. Expected sequence:
```
postgres    | database system is ready
redis       | Ready to accept connections
ingestion   | Catalogue sync: 30 cameras upserted
ingestion   | Starting Camera 1 → rtsp://live.corp8.cloud:8554/stream/1
ai_worker   | Loading yolov8n.pt (CPU) ...
ai_worker   | YOLO worker ready (skip=3)
intelligence| Intelligence engine ready
api         | Uvicorn running on 0.0.0.0:8000
```

First run may take 2–3 minutes before all services are healthy.

---

## Step 5 — Open the dashboard

| URL | What it is |
|-----|------------|
| http://localhost:3000 | Live dashboard |
| http://localhost:8000/docs | API explorer (Swagger UI) |
| http://localhost:8000/cameras/ | Camera list (JSON) |

---

## Step 6 — Add to watchlist (demo)

In the dashboard, click **📋 Watchlist → + Add Entry**:

| Field | Value |
|-------|-------|
| Name | Suspect 1 |
| Type | person |
| Alert Priority | HIGH |

Or for a vehicle:

| Field | Value |
|-------|-------|
| Name | GJ03AA1234 |
| Type | vehicle |
| License Plate | GJ03AA1234 |

Once added, any detection matching that plate will fire a **HIGH** alert in real time.

---

## Step 7 — Verify everything is working

```powershell
python scripts/test_system.py
```

You need Python installed locally for this script. If not, check Redis directly:
```powershell
docker compose exec redis redis-cli XLEN raw_frames
docker compose exec redis redis-cli XLEN detections
docker compose exec redis redis-cli XLEN alerts
```
After 1–2 minutes, all three should be > 0.

---

## Useful commands

```powershell
# View live logs for a specific service
docker compose logs -f ai_worker
docker compose logs -f intelligence
docker compose logs -f ingestion

# Restart a single service
docker compose restart ai_worker

# Stop everything
docker compose down

# Stop and wipe database (full reset)
docker compose down -v

# Check camera catalogue from live server
curl http://live.corp8.cloud/api/ingest
```

---

## Performance expectations on Intel Iris CPU

| Metric | Expected |
|--------|----------|
| Cameras connected | 30 |
| Frame ingest rate | ~90 FPS total (3 FPS × 30 cams) |
| Detection rate | ~1 per camera per second |
| YOLOv8n inference | ~5–8 FPS per worker process |
| ANPR per plate | ~0.3–0.5 s |
| Face embedding | ~0.5–1 s |
| Alert latency | 2–5 seconds from event to dashboard |
| CPU usage | 70–90% (4 YOLO + 3 other workers) |
| RAM usage | ~7–9 GB total across all containers |

> Tip: If CPU is maxed and alerts are slow, reduce `YOLO_WORKERS=2` in `.env`
> and restart: `docker compose up`

---

## Troubleshooting

**"No snapshot available yet"** in dashboard  
→ Wait 30–60 s for ingestion to connect to RTSP streams

**Camera grid shows "Connecting…" for a long time**  
→ Check ingestion logs: `docker compose logs ingestion`  
→ Verify live.corp8.cloud is reachable: open http://live.corp8.cloud in browser

**Out of memory error**  
→ Increase Docker memory to 12 GB in Docker Desktop settings  
→ Or reduce `YOLO_WORKERS=2` and `FACE_ENABLED=false` in `.env`

**Port 3000 already in use**  
→ Change dashboard port in docker-compose.yml: `"3001:80"`

**docker compose: command not found**  
→ Use `docker-compose` (with hyphen) for older Docker Desktop versions

---

## Submission checklist (deadline: 29 August 2026)

- [ ] All 30 cameras showing live feeds
- [ ] Real-time alerts firing in dashboard
- [ ] Plate search working (`/search/plate?q=GJ03`)
- [ ] Watchlist match alerts firing
- [ ] Cross-camera sighting alerts showing
- [ ] Map view shows camera locations + alert pulses
- [ ] `/api/ingest` is the source of truth (not hardcoded streams)
- [ ] TCP transport confirmed (check ingestion logs — no UDP)
- [ ] `scripts/test_system.py` passes all checks

---

*Category 1 · Student Developer · Gujarat Police Innovation Challenge 2026*
