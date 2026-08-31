# Iteration 1 — P0 Production Feed Recovery

## Objective
Restore a production-grade end-to-end live camera data plane using only the current `cctv.corp8.cloud` infrastructure, then prove the path through ingestion and AI before starting P1.

## Audit-derived facts
- CCTV password-only login works and creates a session cookie.
- `https://cctv.corp8.cloud/cameras.json` returns the current camera catalogue with `cam01...cam30` identifiers.
- RTSP `103.250.160.189:8554` has been verified from the operator host with OpenCV.
- The actual AI Compose service is `ai_worker`; it already produces YOLO and ANPR/OCR activity.
- `live.corp8.cloud` is deprecated and must not be used by the production data plane.
- PostgreSQL is the current persistence layer; the earlier audit used stale `plate_text`/`watchlist_entries` assumptions and must not drive refactoring.

## P0 implementation scope
### P0-A Current CCTV source migration
- Replace the deprecated ingestion catalogue dependency with the authenticated current CCTV catalogue.
- Keep the CCTV password server-side in `CCTV_PASSWORD`.
- Build canonical RTSP URLs from `camNN` IDs using the verified RTSP host/port.
- Store current CCTV provenance in `source_system` and canonical `external_id`.

### P0-B Authenticated browser playback
- Add an API-owned CCTV gateway session.
- Add a same-origin `/api/cctv/{asset}` proxy.
- Proxy HLS manifests, media segments and keys through the authenticated upstream session.
- Rewrite HLS resource references so child requests remain same-origin/authenticated.
- Do not expose the provider password to the dashboard.
- Camera API output maps current CCTV HLS URLs to the authenticated proxy path.

### P0-C Camera identity
- Canonical ID format is `cam01` through `cam30`.
- Registry keeps numeric `stream_id` and canonical provider `external_id`.
- HLS and RTSP paths use the same canonical identity.

### P0-D Ingestion transport and recovery
- Force OpenCV FFmpeg RTSP transport to TCP.
- Bounded reconnect cycle with backoff.
- Explicit frame read failure handling.
- Increment reconnect/decode-failure counters.
- Preserve PTS for frame events.
- Detect PTS backwards/large-forward jumps and publish `cam_resets`.
- AI worker already consumes `cam_resets` and resets per-camera tracker/voting state.

### P0-E Runtime observability
The ingestion worker now persists/records:
- observed width/height
- source FPS
- decoded FPS
- published FPS
- codec
- last frame timestamp
- observed timestamp
- reconnect count
- decode failure count
- connectivity/health state

It also emits periodic telemetry logs so frame flow can be proven without injecting diagnostic code.

## Files changed in Iteration 1
- `docker-compose.yml`
- `ingestion/catalogue_sync.py`
- `ingestion/worker.py`
- `api/services/cctv_gateway.py`
- `api/routes/cctv.py`
- `api/main.py`
- `api/models.py`
- `api/requirements.txt`
- `.env.example`

## Required local configuration
Do not commit the real CCTV password. Add to the local `.env`:

```text
POSTGRES_PASSWORD=sentinel
CCTV_PASSWORD=<assigned-current-feed-password>
RTSP_HOST_IP=103.250.160.189
RTSP_PORT=8554
```

The database URL inside Docker remains:

```text
postgresql://sentinel:${POSTGRES_PASSWORD}@postgres:5432/sentinel
```

## Deployment procedure
1. Pull the latest `main`.
2. Set `CCTV_PASSWORD` in the local uncommitted `.env`.
3. Validate Compose before touching running services:

```powershell
docker compose config
```

4. Build only the affected application images:

```powershell
docker compose build api ingestion dashboard ai_worker
```

5. Recreate the P0 data-plane services:

```powershell
docker compose up -d postgres redis api ingestion ai_worker dashboard
```

6. Wait for health:

```powershell
docker compose ps
```

7. Check ingestion logs:

```powershell
docker compose logs --tail=200 ingestion
```

Expected new evidence:
- `CCTV catalogue authenticated successfully`
- `CCTV catalogue sync: 30 cameras upserted`
- `Opening RTSP/TCP source for ...`
- `connected; source_fps=...`
- telemetry lines containing `frames=... published=...`

The following are now considered legacy/regression signals and must not appear:
- `live.corp8.cloud`
- `INGEST_API`
- `502 Bad Gateway` for the retired ingest API
- `Empty catalogue` caused by the retired endpoint

8. Check AI worker:

```powershell
docker compose logs --tail=200 ai_worker
```

Expected:
- YOLO model load
- frame consumption/detection activity
- ANPR request/OCR activity

9. Check Redis streams:

```powershell
docker compose exec redis redis-cli XLEN raw_frames
docker compose exec redis redis-cli XLEN detections
docker compose exec redis redis-cli XLEN anpr_requests
```

10. Check API CCTV proxy from the logged-in dashboard. The camera API should return `/api/cctv/camNN/index.m3u8` for current CCTV cameras.

## P0 acceptance gate
Iteration 1 is complete only when all of the following are true:

```text
Current CCTV authentication       PASS
Catalogue = 30 current cameras    PASS
cam01...cam30 identity            PASS
RTSP TCP + first frame            PASS
Ingestion frame telemetry         PASS
raw_frames Redis stream            PASS
ai_worker YOLO activity           PASS
AI ANPR activity                  PASS
Dashboard HLS through API proxy   PASS
No live.corp8.cloud dependency     PASS
```

Only after this gate is green should P1 start.

## Explicit non-goals for Iteration 1
Do not change:
- ANPR thresholds
- plate normalization business rules
- investigation routing
- watchlist logic
- alert deduplication policy
- face thresholds
- camera import business rules

Those belong to P1/P2 and should be evaluated on a healthy feed plane.
