# Sentinel AI — Gujarat Police CCTV Surveillance & Intelligence Platform

## Evaluator Quick Start (60 seconds)

| Step | Action |
|------|--------|
| 1 | Watch **Video 03** (Test Mode) first — full watchlist, evidence, investigation demo |
| 2 | Watch **Video 04** (Government Feed) — 30 live cameras from `cctv.corp8.cloud` |
| 3 | Open platform URL and sign in with VIEWER credentials from submission `07_Platform_Access.txt` |
| 4 | Read `docs/submission/OUTPUT_REPORT.md` for measured detection data |

**Dual-demo strategy:** Production Monitor proves live government CCTV integration. Test Mode proves every intelligence capability end-to-end on controlled footage — same pipeline, isolated from operational records.

- Submission package: [`docs/submission/README.md`](docs/submission/README.md)
- High-level design: [`docs/submission/HLD.md`](docs/submission/HLD.md)
- Developer setup: [`SETUP.md`](SETUP.md)

> Production-grade surveillance, GIS intelligence, vehicle journey tracing, and automated watchlist alerting for Gujarat Police.

---

## 📑 Table of Contents

1. [Executive Summary](#-executive-summary)
2. [Key Capabilities & Innovations](#-key-capabilities--innovations)
3. [System Architecture](#-system-architecture)
4. [Computer Vision & AI Inference Engine](#-computer-vision--ai-inference-engine)
5. [Database Architecture & Connection Pooling](#-database-architecture--connection-pooling)
6. [Test Mode — Miniature Production Parity](#-test-mode--miniature-production-parity)
7. [CCTV Video Assets Catalogue](#-cctv-video-assets-catalogue)
8. [GIS & Map Intelligence](#-gis--map-intelligence)
9. [Role-Based Access Control (RBAC) & Security](#-role-based-access-control-rbac--security)
10. [Docker Services & Port Allocations](#-docker-services--port-allocations)
11. [Quick Start & Deployment Guide](#-quick-start--deployment-guide)
12. [Verification, CI Gates & Testing](#-verification-ci-gates--testing)
13. [API Endpoints Reference](#-api-endpoints-reference)

---

## 🏛️ Executive Summary

**Sentinel** is an end-to-end intelligent CCTV monitoring, geospatial analytics, ANPR (Automatic Number Plate Recognition), facial recognition, and automated threat alert dispatch system developed for the **Gujarat Police Innovation Challenge 2026**.

Addressing the complexity of **26 independent government departments** managing heterogeneous CCTV networks across Gujarat, Sentinel provides a unified **Model 1 Centralized CCTV Registry**, high-throughput stream ingestion, GPU/CPU-accelerated AI vision pipelines, GIS vehicle journey mapping, and a strict **Miniature-Production Test Mode** operating on real CCTV video assets.

---

## ⚡ Key Capabilities & Innovations

- **Unified Camera Registry & GIS Mapping:** PostGIS-ready camera tracking with verified Gujarat coordinates across Ahmedabad, Gandhinagar, Surat, Vadodara, and Rajkot with MarkerCluster grouping, health status, and live route replay.
- **High-Throughput Stream Ingestion:** Multi-protocol support (RTSP over TCP, authenticated HLS proxy, WebRTC/WHEP) with per-process database connection pooling preventing connection exhaustion across 30+ simultaneous streams.
- **Real-Time ANPR & Multi-Camera Vehicle Tracking:** EasyOCR-powered plate recognition with Indian state syntax validation (e.g. `GJ-01-AB-1234`), confidence gating, and cross-camera vehicle journey reconstruction (`/search/plate/journey`).
- **Facial Recognition & $O(1)$ FAISS Watchlist Matching:** InsightFace 512-dimensional ArcFace vector extraction with `faiss.IndexFlatIP` cosine similarity acceleration and graceful numpy fallbacks.
- **Real-Time Anomaly & Crowd Detection:** Person-aware crowd formation and rapid dispersion/running detection with bounding box spatial tracking.
- **Enterprise Alert Lifecycle & WebSocket Dispatch:** 4-tier alert priority (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), Redis SETNX deduplication cooldown, instant WebSocket push notifications, and auditable status transitions (`NEW` → `ACKNOWLEDGED` → `RESOLVED`).
- **Test Mode Parity:** Zero fake mock pipelines. Test Mode executes the exact same contract pipelines (isolated Redis streams `test:raw_frames`, session-scoped PostgreSQL tables, real MediaMTX RTSP feeds, and interactive GIS mapping) with complete session isolation.

---

## 🏗️ System Architecture

```
                                  [ Heterogeneous CCTV Network ]
                     (RTSP / HLS / WebRTC / Video Test Files / MediaMTX)
                                              │
                                              ▼
                                 [ Ingestion Subsystem ]
                     (worker.py / test_runner.py / stream_adapters.py)
                     • SimpleConnectionPool(1, 5) per worker process
                     • Frame extraction & JPEG encoding @ target FPS
                                              │
                                              ▼
                                    [ Redis Stream Bus ]
                     • Production: raw_frames | Test: test:raw_frames
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
         [ AI Computer Vision Engine ]                      [ Person Investigation ]
  (YOLOv8 + DeepSORT + ANPR + InsightFace)               (On-demand facial search & match)
  • Vehicle & Person Detection (YOLOv8n)                 • ArcFace 512-dim embedding engine
  • ANPR OCR Engine (EasyOCR + Rule Filter)              • Cosine similarity search
  • Behavior & Crowd Anomaly Detection
                    │                                                   │
                    └─────────────────────────┬─────────────────────────┘
                                              ▼
                               [ Intelligence Subsystem ]
                     • ThreadedConnectionPool(2, 10) shared store
                     • FAISS IndexFlatIP Watchlist Correlation (Plate + Face)
                     • Multi-camera Sighting Store & Route Assembler
                     • Alert Engine with Redis SETNX Deduplication
                                              │
                                              ▼
                                [ PostgreSQL / PostGIS DB ]
                     • Cameras Registry & Geospatial Index (GIST)
                     • Sighting Store & Global Journeys
                     • Alerts, Watchlists & Immutable Audit Logs
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
            [ FastAPI Backend ]                                [ React Frontend UI ]
  • RESTful API (CRUD, Search, Onboarding)               • Real-time Multi-column Camera Grid
  • WebSocket Alert Dispatch Manager                     • Leaflet GIS Gujarat Map & Journeys
  • JWT Auth & 6-Tier Role-Based Access Control          • Investigation & Watchlist Workspaces
  • Authenticated CCTV Proxy Gateway                     • Test Mode Diagnostics & Feed Manager
```

---

## 🧠 Computer Vision & AI Inference Engine

1. **Object Detection & Multi-Object Tracking:**
   - Model: **YOLOv8** (optimized for person, vehicle, motorbike, bus, truck classes).
   - Tracker: **DeepSORT** with Kalman filtering and bounding box re-identification across occlusions.
2. **Automatic Number Plate Recognition (ANPR):**
   - Preprocessing: Adaptive thresholding, contrast enhancement, and aspect-ratio bounding box filtering.
   - Text Recognition: **EasyOCR** with Indian standard plate grammar validation (`GJ01XX1234`, `GJ-18-..`).
   - Confidence Gating: Minimum OCR confidence threshold (configured via `ai_engine/thresholds.yaml`).
3. **Facial Feature Extraction & Matching:**
   - Architecture: **InsightFace / ArcFace** yielding 512-dimensional normalized feature embeddings.
   - Vector Index: `faiss.IndexFlatIP` performing sub-millisecond inner-product search over registered police watchlists.
4. **Crowd & Behavioral Anomaly Detection:**
   - Motion velocity and bounding-box density analytics detect sudden crowd dispersal, rapid running, and abnormal crowd formations.

---

## 🗄️ Database Architecture & Connection Pooling

To guarantee robust operation under heavy concurrent ingestion (30+ live camera processes), Sentinel enforces structured connection pooling:

- **Per-Process Ingestion Pooling:** `ingestion/worker.py` utilizes `psycopg2.pool.SimpleConnectionPool(1, 5)` per camera child process to prevent connection starvation.
- **Thread-Safe Intelligence Pooling:** `intelligence/sighting_store.py` manages `psycopg2.pool.ThreadedConnectionPool(2, 10)` with clean `_get_conn()` and `_put_conn()` context safety shared with `alert_engine.py`.
- **Geospatial Indexing:** PostGIS `GEOMETRY(Point, 4326)` with GiST indexes for sub-5ms proximity and bounding-box queries.
- **Audit Logging:** Every camera creation, modification, import, and alert transition writes immutable records to `camera_audit_log` with actor metadata.

---

## 🧪 Test Mode — Miniature Production Parity

Test Mode is **not a fake UI or static mock**. It is a fully functional, deterministic miniature production system:

| Layer | Production Mode | Test Mode | Parity Mechanism |
|---|---|---|---|
| **Stream Bus** | `raw_frames` Redis stream | `test:raw_frames` Redis stream | Complete namespace separation |
| **Media Gateway** | Live CCTV / RTSP feeds | MediaMTX RTSP feeds from MP4s | Identical HLS / RTSP playback pipeline |
| **Database** | `cameras`, `sightings`, `alerts` | `session_cameras`, `test_sightings`, `test_alerts` | Session-scoped UUID isolation |
| **Watchlists** | `watchlist` table | `test_watchlists` table | Dedicated isolated test watchlist rules |
| **GIS Mapping** | Live camera coordinates | Verified Gujarat test geodata | Full Leaflet marker, popup & route parity |
| **Alert Engine** | Production alert engine | `test_sighting_store.py` alert engine | Identical schema, statuses & transitions |

---

## 📹 CCTV Video Assets Catalogue

Sentinel includes 9 high-definition CCTV video assets in the `videos/` directory for deterministic testing and demonstration:

| Video Asset | Scenario / Purpose | Tested AI Pipelines |
|---|---|---|
| `Automatic Number Plate Recognition (ANPR) _ Vehicle Number Plate Recognition (1).mp4` | High-accuracy vehicle registration plate capture | ANPR OCR, Sighting Store, Journey Tracing |
| `Fixed_CCTV_Crowd_Running.mp4` | Sudden crowd running & rapid dispersal | Behavior Analysis, Anomaly Alert Generation |
| `Fixed_CCTV_surveillance_camera.mp4` | Fixed surveillance camera perimeter monitoring | Person Detection, DeepSORT Multi-tracking |
| `Traffic Control CCTV.mp4` | Multi-lane junction vehicle traffic monitoring | Vehicle Counting, ANPR, Congestion Flow |
| `pexels-casey-whalen-6571483 (2160p).mp4` | Urban street pedestrian and vehicle surveillance | Person & Vehicle Detection, Face Matching |
| `pexels-christopher-schultz-5927708 (1080p).mp4` | High-definition commercial street monitoring | Multi-camera Re-ID, Sighting Tracking |
| `pexels-kelly-13998984 (1080p).mp4` | Dense pedestrian pathway monitoring | Crowd Density, Person Investigation |
| `pexels-kelly-13999008 (1080p).mp4` | Wide-angle public intersection surveillance | Cross-camera Tracking, Vehicle Journey |
| `pexels-taryn-elliott-5309381 (2160p).mp4` | High-resolution public square monitoring | Person Investigation, Face Watchlist Match |

---

## 🗺️ GIS & Map Intelligence

Sentinel features a high-performance Leaflet-based GIS mapping interface designed for Gujarat Police operations:
- **Gujarat Geographic Bounding:** Pre-bounded to Gujarat coordinates (`[20.0, 68.0]` to `[24.7, 74.5]`).
- **Camera Marker Clustering:** `react-leaflet-cluster` groups dense camera networks with color-coded status rings (Online, Degraded, Offline).
- **Interactive Popup & Live Feed View:** Instant camera metadata inspection, live snapshot preview, and one-click transition to full-screen monitoring.
- **Vehicle Journey Route Tracking:** Visualizes the sequential movement of target vehicles across cameras with timestamped waypoints, directional polyline arrows, and journey statistics.
- **Alert Visualizer:** Real-time flashing markers on cameras with active unacknowledged alerts (`CRITICAL` red, `HIGH` orange, `MEDIUM` yellow).

---

## 🔒 Role-Based Access Control (RBAC) & Security

Sentinel implements enterprise-grade authentication and cryptographic access controls:

| Role | Permissions & Capabilities |
|---|---|
| **SUPERADMIN** | Full system control: camera administration, user management, audit review, watchlist editing, alert operations. |
| **ADMIN** | Camera onboarding, bulk import, vendor management, watchlist management, alert operations. |
| **INVESTIGATOR** | Full search & investigation: plate journeys, photo face search, evidence export, alert review. |
| **OPERATOR** | Live feed monitoring, alert acknowledgment and resolution, camera locator. |
| **AUDITOR** | Read-only access to camera registry, audit logs, and compliance reporting. |
| **VIEWER** | Read-only monitoring of live camera feeds and GIS map. |

### Security Safeguards
- **HMAC Signed Asset Tokens:** Snapshots and evidence assets are protected by short-lived HMAC-SHA256 signed URLs.
- **Credential Masking:** CCTV camera passwords and RTSP URLs are sanitized server-side and never exposed to client browsers.
- **CCTV Gateway Proxy:** Same-origin authenticated proxy `/api/cctv/camXX/index.m3u8` eliminates CORS issues and secures stream transport.

---

## 🐳 Docker Services & Port Allocations

| Service Name | Port | Description |
|---|---|---|
| **dashboard** | `3000` | React single-page application operator interface |
| **api** | `8000` | FastAPI REST API, WebSocket server, and CCTV proxy |
| **postgres** | `5432` | PostgreSQL database with PostGIS and pgvector extensions |
| **redis** | `6379` | In-memory message bus, Redis streams, and cache |
| **mediamtx** | `8554` / `8888` | RTSP / HLS media streaming server for CCTV & test feeds |
| **ingestion** | — | Production multi-camera frame extraction worker |
| **ai_worker** | — | YOLOv8, DeepSORT, and EasyOCR inference engine |
| **intelligence** | — | Watchlist matching, sighting store, and alert generation |
| **person_investigation** | — | Dedicated on-demand facial recognition search worker |

---

## 🚀 Quick Start & Deployment Guide

### Prerequisites
- Docker Engine 24.0+ and Docker Compose v2
- 8 GB RAM minimum (16 GB recommended for multi-stream AI processing)
- Supported OS: Linux, macOS, Windows 10/11 with WSL2

### 1. Clone & Configure Environment

```bash
# Clone the repository
git clone https://github.com/Nirmal-Yash/Sentinal-Gujarat-Police.git
cd Sentinal-Gujarat-Police

# Initialize environment configuration
cp .env.example .env      # On Linux / macOS
# or
Copy-Item .env.example .env # On Windows PowerShell
```

Copy `.env.example` to `.env` and replace all `replace-with-*` placeholders with strong secrets before deployment.

### 2. Build & Launch Docker Services

```bash
docker compose config -q
docker compose up -d --build
```

### 3. Access Sentinel

- **Web Dashboard:** [http://localhost:3000](http://localhost:3000)
- **Interactive API Documentation (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Default Superadmin Login:** Username: `admin` | Password: (as set in `.env`)

---

## 🧪 Verification, CI Gates & Testing

Sentinel maintains a comprehensive testing and validation harness with 100% pass rate:

```bash
# Run unit and contract test suite (58 tests)
python -m pytest

# Run CI Gate validation
python scripts/final_ci_gate.py

# Run Integration Gate validation
python scripts/final_integration_gate.py

# Run Refactor & Parity Gate validation
python scripts/validate_refactor.py
```

---

## 📡 API Endpoints Reference

### Cameras & Registry
- `GET /api/cameras` — List all registered cameras with health and GIS metadata.
- `POST /api/cameras/onboard` — Onboard a single camera with validation.
- `POST /api/cameras/import` — Bulk import camera registry via CSV or XLSX.
- `GET /api/cameras/{id}/snapshot` — Fetch latest HMAC-signed camera frame snapshot.

### CCTV Stream Proxy
- `GET /api/cctv/cam{id}/index.m3u8` — Authenticated HLS stream manifest proxy.
- `GET /api/cctv/cam{id}/{segment}.ts` — Authenticated HLS video transport segment.

### Alerts & Intelligence
- `GET /api/alerts` — Query alerts with multi-criteria filtering (priority, status, date range).
- `GET /api/alerts/stats/counts` — Get live alert counts grouped by priority and status.
- `POST /api/alerts/{id}/transition` — Transition alert lifecycle (`ACKNOWLEDGED`, `RESOLVED`).

### Search & Investigations
- `GET /api/search/plate` — Search vehicle sightings across all cameras.
- `GET /api/search/plate/journey` — Generate sequential GIS journey for a license plate.
- `POST /api/search/person/match` — On-demand photo search against historical face sightings.

### Watchlists
- `GET /api/watchlist` — Retrieve active person and vehicle watchlists.
- `POST /api/watchlist` — Register a new target plate or face with alert priority.

### Test Mode Subsystem
- `POST /api/test/sessions` — Initialize a new isolated test session.
- `GET /api/test/catalogue` — List available video assets from `videos/`.
- `POST /api/test/feeds` — Add a test video feed to the active session.
- `GET /api/test/results/{session_id}` — Retrieve detections, sightings, and alerts for test session.

