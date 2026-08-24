# 🛡️ Sentinel AI — Gujarat Police Innovation Challenge 2026

AI-powered unified CCTV surveillance platform.  
Single developer · Single machine · 100% open-source · ₹0 cost

---

## Architecture

```
Camera Simulator (mediamtx RTSP)
        ↓  RTSP pull
Ingestion Workers (opencv · onvif-zeep · ffmpeg)
        ↓  Redis Stream: raw_frames
AI Analytics Workers (YOLOv8 · EasyOCR · InsightFace · DeepSORT · OpenCV)
        ↓  Redis Stream: detections
Intelligence Engine (FAISS · cross-camera re-ID · watchlist match)
        ↓  Redis Stream: alerts
API + Dashboard (FastAPI · WebSocket · React · Leaflet.js)
        ↕  PostgreSQL + pgvector · Redis · FAISS
```

---

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- 8 GB RAM minimum (16 GB recommended for AI models)
- 20 GB free disk space (AI model downloads ~4 GB)

---

## Quick Start

```bash
# 1. Clone / copy this project
cd sentinel-ai

# 2. Copy environment file
cp .env.example .env

# 3. Generate test camera videos (one-time, ~3 min)
mkdir -p camera_sim/videos
docker-compose run --rm generate_videos

# 4. Start everything
docker-compose up --build

# 5. (Optional) Seed watchlist with demo embeddings
docker-compose exec intelligence python /app/scripts/seed_watchlist.py
```

**Dashboard → http://localhost:3000**  
**API docs  → http://localhost:8000/docs**

---

## Services

| Service       | Port  | Description                             |
|---------------|-------|-----------------------------------------|
| redis         | 6379  | Message bus + snapshot cache            |
| postgres      | 5432  | Events, alerts, watchlist, tracks       |
| mediamtx      | 8554  | RTSP camera simulator                   |
| ingestion     | —     | Frame extraction → raw_frames stream    |
| ai_worker     | —     | YOLOv8 · ANPR · FaceNet · Behavior AI  |
| intelligence  | —     | Cross-camera tracking · watchlist match |
| api           | 8000  | FastAPI REST + WebSocket                |
| dashboard     | 3000  | React dashboard (nginx)                 |

---

## Key API Endpoints

```
GET  /cameras/                    List all cameras
GET  /cameras/{id}/snapshot       Live JPEG snapshot
GET  /alerts/?priority=HIGH       Filter alerts
POST /alerts/{id}/acknowledge     Acknowledge alert
GET  /watchlist/                  View watchlist
POST /watchlist/                  Add to watchlist
GET  /search/plate?q=GJ03AA1234  Search by plate
GET  /search/track/{id}          Track across cameras
WS   /ws/alerts                  Real-time alert stream
```

---

## Technology Stack (all open-source, zero cost)

| Component        | Library                | License      |
|------------------|------------------------|--------------|
| Object detection | ultralytics (YOLOv8n)  | AGPL-3.0     |
| Number plates    | EasyOCR                | Apache-2.0   |
| Face embeddings  | InsightFace ArcFace    | MIT          |
| Object tracking  | deep-sort-realtime     | MIT          |
| Behavior AI      | OpenCV optical flow    | Apache-2.0   |
| ANN search       | FAISS (faiss-cpu)      | MIT          |
| Message bus      | Redis 7 Streams        | BSD-3        |
| Database         | PostgreSQL 16          | PostgreSQL   |
| Vector search    | pgvector               | PostgreSQL   |
| API framework    | FastAPI                | MIT          |
| Frontend         | React 18 + Leaflet.js  | MIT / BSD-2  |
| Container        | Docker CE              | Apache-2.0   |

**Total cost: ₹0**

---

## Development

```bash
# View logs per service
docker-compose logs -f ai_worker
docker-compose logs -f intelligence
docker-compose logs -f api

# Run health check
python scripts/test_system.py

# Inspect Redis streams
docker-compose exec redis redis-cli XLEN raw_frames
docker-compose exec redis redis-cli XLEN detections
docker-compose exec redis redis-cli XLEN alerts

# Add to watchlist via API
curl -X POST http://localhost:8000/watchlist/ \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Suspect","entity_type":"person","alert_priority":"HIGH"}'
```

---

## Stage 2 Demo Scenario

1. Start system: `docker-compose up`
2. Open dashboard: http://localhost:3000
3. Go to **Watchlist → Add Entry** → add a plate number (e.g. GJ03AA1234)
4. Watch the AI detect vehicles → plates matched → HIGH alert fires in real time
5. Switch to **Map View** → see alert pulse on camera location
6. Use **Search → License Plate** → full detection history

---

*Built for Gujarat Police Innovation Challenge 2026 · Category 1*
