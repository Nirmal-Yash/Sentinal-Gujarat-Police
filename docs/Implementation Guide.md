## 1 — Verify System State (from actual code)

| Claim in architecture-decisions.md | Actual code state | Verdict |
|---|---|---|
| PostGIS canonical registry | `FLOAT lat, lng` — no geometry column | **NOT implemented** |
| CSV onboarding + audit history | No endpoint, no tables | **NOT implemented** |
| Observed stream metadata | `stream_metadata JSONB` + Redis key — ✓ | **Implemented** |
| Indexed registry/plate search | GIN FTS index on cameras — ✓ | **Implemented** |
| Durable vehicle sightings | `_persist_plate()` in intelligence/main.py — ✓ | **Implemented** |
| Restart-safe alert dedup | In-memory dict in `alert_engine.py` — resets on restart | **NOT restart-safe** |
| Compact Gujarat GIS | `fitBounds(GUJARAT_BOUNDS)` on init — ✓ | **Implemented** |
| Camera clustering/layers | MarkerCluster + coverage group — ✓ | **Implemented** |
| Persistent UI preferences | localStorage cols + view — ✓ | **Implemented** |
| Journey route from `/search/track/{id}` | Endpoint exists; returns empty — `global_track_id` never written to DB | **Broken** |
| Manual camera entry | No endpoint, no UI | **NOT implemented** |
| Vendor management | Not in schema or code | **NOT implemented** |

Don't Refer Verdict but analyze yourself and Decide.

---

## 2 — Disclaimer Resolutions

**D2 — Alert dedup not restart-safe**
Replace `_plate_seen` dict in `alert_engine.py` with Redis SETNX + TTL:
```
key = alert_dedup:{cam_id}:{alert_type}:{hash(details)}
SETNX → returns 0 if key exists → suppress alert
EXPIRE key COOLDOWN_SECS → auto-expires = no manual cleanup
```
Survives unlimited restarts. Same pattern for intelligence/main.py plate cooldown dict.

**D3 — FAISS in-memory only**
Three-layer persistence strategy:
- Layer 1 (hot): FAISS index serialized to Redis key `faiss:track_index` every 30 seconds via `faiss.serialize_index()`; TTL = 10 minutes
- Layer 2 (warm): `global_tracks` table in PostgreSQL — every assigned `global_id` writes `(id, entity_type, first_seen_cam, last_seen_cam, first_seen_at, last_seen_at, cam_history JSONB, embedding vector(512))`
- Layer 3 (rebuild): On intelligence startup — try Redis first, fall back to reconstructing FAISS index from PostgreSQL embeddings
- Net result: restart loses at most 30 seconds of tracking state

**D4 — camera_audit_log + camera_imports functional plan**
Tables:
```sql
camera_imports(id UUID, filename, status ENUM(pending/processing/done/failed),
  total_rows INT, success_rows INT, error_rows INT,
  column_map JSONB, errors JSONB, actor VARCHAR, created_at)

camera_audit_log(id UUID, cam_id UUID, action ENUM(create/update/delete/import),
  actor VARCHAR, correlation_id UUID, role VARCHAR,
  before_state JSONB, after_state JSONB, ts TIMESTAMPTZ)
```
Implementation: SQLAlchemy `@event.listens_for(Camera, 'after_insert/update/delete')` triggers audit log write. Every mutating API route passes `actor` from JWT claims. Import job writes one audit row per camera created/updated.

**D5 — Manual camera entry: NOT implemented → Fix**
`POST /cameras/onboard` endpoint needed. Fields: all Model-1 registry columns + vendor_id. Returns camera UUID. Writes audit log. Validates duplicate `(stream_id, rtsp_url)`.

**D6 — Vendor management: NOT in schema → Fix**
See Section 4 below.

**D7 — PostGIS: practical scalable solution**
Decision: Add PostGIS geometry column alongside existing lat/lng FLOATs. Use `postgis/postgis:16-3.4` Docker image (replaces `pgvector/pgvector:pg16`). Note: `pgvector` extension available in PostGIS image too.

Schema change:
```sql
ALTER TABLE cameras ADD COLUMN geom GEOMETRY(POINT, 4326);
UPDATE cameras SET geom = ST_SetSRID(ST_MakePoint(lng, lat), 4326) WHERE lat != 0 AND lng != 0;
CREATE INDEX idx_cameras_geom ON cameras USING GIST(geom);
-- Trigger: keep geom in sync with lat/lng on every update
CREATE OR REPLACE FUNCTION sync_camera_geom() RETURNS trigger AS $$
BEGIN NEW.geom := ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326); RETURN NEW; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_camera_geom BEFORE INSERT OR UPDATE ON cameras FOR EACH ROW EXECUTE FUNCTION sync_camera_geom();
```

Benefits at 85,000 cameras: `ST_DWithin` (cameras within Xkm of incident), `ST_Within` (cameras inside geofence polygon), coverage density heatmap via `ST_Buffer`. GiST index handles spatial queries in <5ms even at 85k rows.

Coordinate seeding: 30-row SQL file from table above; `coord_source`, `coord_confidence` columns distinguish manual/imported/geocoded/default tiers. Cascade rule encoded in `catalogue_sync.py`: never overwrite a higher-confidence coordinate with a lower-confidence one.

**D8 — global_track_id never persisted → Fix**
In `intelligence/main.py`, after `tracker.assign()` returns `global_id`:
1. Write to `detections` table: `(cam_id, detection_type='face', confidence, pts_ms, bbox, global_track_id=global_id, embedding)`
2. Upsert `global_tracks`: `INSERT ... ON CONFLICT(id) DO UPDATE SET last_seen_cam, last_seen_at, cam_history = cam_history || [{cam_id, ts}]`
3. Same dedup as plates: suppress re-insert within 5 seconds per `(global_id, cam_id)` pair

Now `/search/track/{id}` returns real camera-crossing journey data.

---

## 3 — RBAC Implementation Plan

**Role matrix:**

| Permission | SUPERADMIN | ADMIN | OPERATOR | VIEWER |
|---|---|---|---|---|
| View cameras / alerts / map | ✓ | ✓ | ✓ | ✓ |
| Search plates / tracks | ✓ | ✓ | ✓ | read-only |
| Acknowledge alerts | ✓ | ✓ | ✓ | ✗ |
| Add/edit watchlist | ✓ | ✓ | ✗ | ✗ |
| Onboard cameras (manual/CSV) | ✓ | ✓ | ✗ | ✗ |
| Manage vendors | ✓ | ✓ | ✗ | ✗ |
| View import/audit history | ✓ | ✓ | ✗ | ✗ |
| Manage users | ✓ | ✗ | ✗ | ✗ |
| System config / test mode | ✓ | ✗ | ✗ | ✗ |

**Backend implementation:**
```
users(id UUID, username, email, password_hash, role ENUM, is_active, created_at, last_login)
user_sessions(id UUID, user_id FK, jti UUID UNIQUE, expires_at, revoked BOOL, created_at)
```

Auth flow:
- `POST /auth/login` → validates credentials → returns JWT `{sub: user_id, role, jti, exp}`
- `POST /auth/logout` → sets `user_sessions.revoked = true` for that jti (token invalidation without waiting for expiry)
- `POST /auth/refresh` → issues new JWT if session not revoked
- FastAPI dependency: `require_role(["ADMIN","SUPERADMIN"])` — checks JWT → checks `user_sessions.revoked` → checks role → 401/403 as appropriate
- All mutating routes protected; all read routes require minimum VIEWER token

**Dashboard implementation:**
- Login page (first route if no valid token in `localStorage`)
- JWT stored in `localStorage` as `sentinel.jwt`; role stored in decoded payload
- `AuthContext` React context: exposes `role`, `user`, `can(permission)` function
- All admin controls (`Add Camera`, `Watchlist`, CSV upload, user management) gated by `can()` — hidden for VIEWER/OPERATOR, not just disabled
- Session expiry: 8-hour tokens; auto-refresh 30 minutes before expiry via background interval
- 401 response from API → clear token → redirect to login

**Security alongside RBAC (fixes D14):**
- nginx TLS termination service added to docker-compose as optional `--profile secure`
- Self-signed cert generated at startup via `openssl req -x509` in nginx entrypoint
- All HTTP → HTTPS redirect in nginx config
- Passwords hashed with `bcrypt` (via `passlib`)
- JWT signed with RS256 (private key in Docker secret / `.env`)
- API rate limiting: `slowapi` middleware, 100 req/min per IP for auth endpoints, 1000/min for data
- `CORS_ORIGINS` in `.env` restricts WebSocket + API to dashboard origin only
- RTSP streams remain TCP-only (RTSPS not feasible without vendor cooperation)

**Seeded default users on first deploy:**
```
superadmin / (generated password printed to stdout once on first run)
admin / (generated)
operator / (generated)
```

---

## 4 — Synthetic Video Test Endpoint

**Design principle:** completely isolated — same AI pipeline code, separate data namespace, zero contamination of production tables.

**Architecture:**

```
Test endpoint namespace:  /test/*
Separate tables:          test_detections, test_alerts, test_tracks (same schema + is_test BOOL)
Separate Redis streams:   test:raw_frames, test:detections, test:alerts
Test RTSP feeds:          mediamtx paths: /test/cam1 ... /test/camN (separate from /stream/1..30)
Test pipeline workers:    same ai_engine code, env var TEST_MODE=true → reads/writes test streams
```

**Endpoints:**
```
POST /test/feeds/upload          multipart video file → stored in /test_videos/
POST /test/sessions              creates test session {id, cameras: [{stream_id, video_file, loop}]}
GET  /test/sessions/{id}/status  active/idle, frames processed, detections count
GET  /test/sessions/{id}/results detections, alerts, plate texts with timestamps
DELETE /test/sessions/{id}       stops feeds, clears test Redis streams, clears test tables for this session
```

**Upload + playback flow:**
- User uploads video(s) via `/test/feeds/upload`
- Server stores in `/test_videos/` volume
- `POST /test/sessions` configures mediamtx to serve these files as `rtsp://mediamtx:8554/test/cam{n}`
- Test-mode ingestion worker spawned per session (subprocess, not Docker service restart)
- AI pipeline reads from `test:raw_frames` stream
- Results written to `test_detections` + `test_alerts` with `session_id` column

**Dashboard integration:**
- "Test Mode" toggle in Navbar (SUPERADMIN/ADMIN only)
- When active: camera grid shows test feeds, alert panel shows test alerts, map shows no change (no real cameras affected)
- Upload panel: drag-drop video files, resolution auto-detected (360p–2160p supported), loop toggle
- "Run Test" button starts session; live progress bar; results table with export
- "Clear Test Data" button calls DELETE endpoint

**Isolation guarantee:** test tables have no FK relationships to production tables. Test Redis streams use different key prefix. Dropping all test data is one SQL DELETE per session_id.

**Detachment path:** when real RTSP feeds are fully stable, the `/test/*` routes are disabled by setting `TEST_ENDPOINT_ENABLED=false` in `.env`. No code changes required. Dashboard toggle simply disappears for that env value.

**Video format support (your library):**
- 360p through 2160p: handled by FFmpeg transcoding in mediamtx
- Audio+video: mediamtx strips audio for RTSP (video-only to pipeline); no issue
- All common codecs (H.264, H.265, VP9, AV1): mediamtx transcodes to H.264 output

---

## 5 — Vendor Management Plan

**Schema:**
```sql
vendors(
  id UUID PK, name VARCHAR(255) UNIQUE, hq_city VARCHAR(100),
  website VARCHAR(255), support_email VARCHAR(255), support_phone VARCHAR(50),
  contract_ref VARCHAR(100), notes TEXT,
  protocol_support TEXT[] DEFAULT '{RTSP,ONVIF}',  -- no proprietary lock-in
  is_active BOOL DEFAULT TRUE, created_at TIMESTAMPTZ
)

camera_models(
  id UUID PK, vendor_id FK → vendors,
  model_name VARCHAR(255), camera_type VARCHAR(50),
  default_codec VARCHAR(20), default_fps FLOAT,
  default_width INT, default_height INT,
  capabilities TEXT[],  -- ['anpr','ptz','ir','audio']
  created_at TIMESTAMPTZ
)

-- cameras table additions:
ALTER TABLE cameras ADD COLUMN vendor_id UUID REFERENCES vendors(id);
ALTER TABLE cameras ADD COLUMN model_id UUID REFERENCES camera_models(id);
ALTER TABLE cameras ADD COLUMN firmware_version VARCHAR(100);
ALTER TABLE cameras ADD COLUMN serial_number VARCHAR(100);
```

**No-lock-in rule enforced at schema level:** `protocol_support` column on vendor records only `RTSP` or `ONVIF` — proprietary protocols not enumerable. Ingestion layer (`stream_adapters.py` seam from architecture-decisions.md) converts all sources to RTSP before the pipeline.

**API endpoints:**
```
GET/POST       /vendors/
GET/PUT/DELETE /vendors/{id}
GET/POST       /vendors/{id}/models
GET            /cameras/?vendor_id=&model_id=   (filter existing list endpoint)
```

**Dashboard admin panel — Vendor tab:**
- Vendor list table: name, city, cameras assigned count, protocol support badges, active toggle
- Add vendor modal: form fields + protocol checkboxes (RTSP/ONVIF only, no proprietary option)
- Camera model sub-list per vendor: model name, type, default specs, capabilities chips
- Camera list filter by vendor: dropdown in camera grid toolbar
- Vendor assignment in camera onboard form: searchable dropdown

---

## 6 — Onboarding UI Plan (Manual + CSV + API)

**Manual Entry — Admin Panel "Add Camera" form:**
Fields grouped in sections:
- Identity: stream_id (auto-suggest next available), name, location, department, ownership
- Vendor: vendor dropdown → model dropdown (cascade)
- Connection: RTSP URL, HLS URL, ONVIF profile, connectivity type
- Location: lat/lng fields + small inline Leaflet mini-map with draggable pin (clicking map sets coordinates)
- Capabilities: checkbox group (ANPR, Face, PTZ, IR, Audio)
- Storage: type, retention days
- Submit → `POST /cameras/onboard` → success toast + camera appears in grid immediately

**CSV Import — Admin Panel "Bulk Import" tab:**
Flow:
1. Upload CSV (drag-drop or file picker)
2. System reads header row → shows column mapper UI: each CSV column → dropdown to system field (or "ignore")
3. Preview first 5 rows with mapping applied
4. "Import" button → `POST /cameras/imports/csv` → returns `job_id`
5. Progress bar polling `GET /cameras/imports/{job_id}` every 2s
6. Results table: success rows count, error rows with reason (missing lat, duplicate stream_id, invalid RTSP URL format)
7. Download error CSV for correction and re-import

**Import history table** in admin panel: filename, date, actor, success/error counts, status badge.

**API onboarding** (for programmatic use):
`POST /cameras/onboard` accepts JSON body with same fields as manual form. Auth required (ADMIN+). Returns `{id, stream_id, created_at}`. Audit log written automatically.

**Coordinate UX for low-confidence entries:**
- Cameras with `coord_confidence < 0.4` shown with amber warning badge in map popup: "Coordinates unverified — click to correct"
- Clicking opens inline editor with draggable pin
- Saving writes `coord_source='manual'`, `coord_confidence=1.0` — highest tier, never overwritten by catalogue sync

---

## 7 — Government Feed — Upstream Drawbacks and Resolutions

**Data quality issues (their responsibility):**

| Issue | Specification | Resolution possible from our side |
|---|---|---|
| 17/30 cameras report `codec:"", fps:0, width:0, height:0` | Stream metadata not populated in `/api/ingest` response — camera encoders not reporting to gateway | Runtime-probe via OpenCV `CAP_PROP_*` in ingestion worker; populate `stream_metadata` on first successful frame |
| No geospatial coordinates anywhere in `/api/ingest` | Gateway returns only location name strings; no lat/lng, no PostGIS WKT | Geocode from location string (Nominatim, 1 req/s); store with `coord_source='geocoded', coord_confidence=0.4–0.85` |
| HLS URLs are relative paths (`/live/stream/1/index.m3u8`) | Full URL not provided; breaks cross-origin browser loading | Prefix `http://live.corp8.cloud` in `catalogue_sync.py` at ingest time |
| Camera 23: bitrate 4001 kbps for 1280×720 H.264 (~6× normal) | Encoder misconfiguration — CBR cap not set; will consume disproportionate bandwidth | Ingest as-is; flag in stream_metadata as `bitrate_anomaly: true`; admin alert via dashboard |
| Camera 26: 2560×1440 HEVC (~4K) on rural panchayat | Oversized stream for location; no operational benefit vs 1080p at detection inference size | Ingest; resize to 1080p in ingestion worker for AI pipeline via `cv2.resize`; store full-res snapshot |
| No authentication on RTSP streams | Any actor with stream URL can connect; no token, no TLS | Beyond our scope — formally document as upstream security gap in submission |
| Mixed H.264 + HEVC without codec declaration for 17 cameras | 17 streams have `codec:""` — cannot pre-configure decoder | OpenCV/FFmpeg auto-detects; log actual codec to `stream_metadata.detected_codec` on first decode |
| No PTZ control metadata | No pan/tilt/zoom capability flags in API | Record `camera_type` as "Fixed" (default) for all; update manually when known |
| No installation angle / FoV data | Coverage area cannot be accurately computed | Coverage rings use fixed radius by type (PTZ: 400m, Fixed: 180m) — document as estimated |
| No uptime / health history in API | `live: true` is current state only; no historical availability | Build from our `last_seen_at` + reconnect logs; `camera_health_observations` table (deferred per architecture doc) |
| No departmental ownership metadata | `department` field absent — only location string | Infer from location (Gram Panchayat → Rural; Bus Port → GSRTC; Police → Gujarat Police); admin can correct |
| Camera numbers non-sequential | `stream_id=21` has location text "23 Patan..."; internal numbering inconsistent | Use `number` field from API as `stream_id`; treat location text as canonical location string only |

---

## 8 — Final Implementation Plan (No Timeline)

### Scope organized by service boundary

**PostgreSQL / Schema:**
- Migrate to `postgis/postgis:16-3.4` image (retains pgvector)
- Add: `geom GEOMETRY(POINT,4326)` + GiST index + sync trigger
- Add: `coord_source`, `coord_confidence` columns with tier cascade
- Add: `vendors`, `camera_models` tables with FKs to `cameras`
- Add: `camera_imports`, `camera_audit_log` tables
- Add: `users`, `user_sessions` tables for RBAC
- Add: `global_tracks` upsert support (table already exists)
- Add: `test_detections`, `test_alerts` tables with `session_id` column
- Coordinate seed: 30-row SQL from verified table above

**API (FastAPI) — new/changed routes:**
```
POST   /auth/login              public
POST   /auth/logout             authenticated
POST   /auth/refresh            authenticated
GET    /auth/me                 authenticated

GET    /users/                  SUPERADMIN
POST   /users/                  SUPERADMIN
PUT    /users/{id}              SUPERADMIN
DELETE /users/{id}              SUPERADMIN

POST   /cameras/onboard         ADMIN+
POST   /cameras/imports/csv     ADMIN+
GET    /cameras/imports/         ADMIN+
GET    /cameras/imports/{id}    ADMIN+

GET    /vendors/                OPERATOR+
POST   /vendors/                ADMIN+
PUT    /vendors/{id}            ADMIN+
GET    /vendors/{id}/models     OPERATOR+
POST   /vendors/{id}/models     ADMIN+

POST   /test/feeds/upload       SUPERADMIN
POST   /test/sessions           SUPERADMIN
GET    /test/sessions/{id}/status     SUPERADMIN
GET    /test/sessions/{id}/results    SUPERADMIN
DELETE /test/sessions/{id}     SUPERADMIN

GET    /reports/detections      ADMIN+   (CSV/JSON, filters: from/to/cam_id/plate)
```

All existing routes: minimum VIEWER JWT required. Mutating routes: OPERATOR+ or ADMIN+ per matrix.

**Ingestion:**
- `catalogue_sync.py`: fix HLS URL prefix, add `bitrate_kbps` to stream_metadata, normalize codec strings, coordinate tier cascade (never downgrade confidence)
- `worker.py`: add `detected_codec` to stream_metadata, bitrate_anomaly flag, resize logic for Camera 26 class streams

**Intelligence:**
- `alert_engine.py`: replace in-memory dedup dict with Redis SETNX+TTL
- `main.py`: 
  - persist face detections + global_track_id to `detections` table
  - upsert `global_tracks` on every cross-camera assignment
  - replace `_plate_cooldown` dict with Redis SETNX
- `cross_camera.py`: add FAISS index serialization to Redis every 30s + rebuild from PostgreSQL on startup

**Dashboard (React) — new/changed:**
- Login page (route `/login`, redirect if no valid JWT)
- `AuthContext`: JWT decode, `can(permission)`, auto-refresh
- Navbar: user badge (name + role), logout button
- Admin panel: new top-level tab (ADMIN+ only)
  - Cameras sub-tab: Add Camera form with inline map pin
  - Import sub-tab: CSV upload + column mapper + progress + history
  - Vendors sub-tab: vendor list + add/edit + models
  - Users sub-tab (SUPERADMIN): user list + add/edit + role assignment
- Test Mode: toggle in Navbar (SUPERADMIN only) → switches to test namespace
  - Upload panel, session controls, results table
- Camera onboard form: coordinate entry with draggable Leaflet mini-map
- Low-confidence coordinate warning badges on map popups
- Report export: button in search results → CSV download

**Docker Compose additions:**
- Replace `pgvector/pgvector:pg16` → `postgis/postgis:16-3.4`
- `nginx` service (optional, `--profile secure`): TLS termination, HTTP→HTTPS redirect
- `test_runner` service: mediamtx + ingestion for test sessions
- Volume: `test_videos:/test_videos`

**Security additions:**
- `passlib[bcrypt]` in API requirements
- `python-jose` for JWT RS256
- `slowapi` rate limiting middleware
- nginx TLS config with self-signed cert generation script
- `.env` updated with `JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`, `ENABLE_TLS`, `TEST_ENDPOINT_ENABLED`

---

## 9 — Questions Before Code Generation

1. **RBAC seeding**: Should default user passwords be auto-generated and printed to stdout once on first run, or should you set them via `.env` before first deploy?

2. **Test endpoint access control**: SUPERADMIN only as planned above, or should ADMIN also have access to run test sessions?

3. **CSV import column mapper**: The mapper UI needs to know which CSV columns are mandatory vs optional. Mandatory minimum is: `name`, `rtsp_url`, `lat`, `lng`. Accept this, or do you want to allow import with only `name + rtsp_url` and use geocoding for missing coordinates?

4. **Inline map pin for camera onboarding form**: Should clicking the map in the Add Camera form auto-fill the lat/lng fields numerically (and the reverse — typing lat/lng moves the pin)? Bidirectional binding is a small extra but good UX.

5. **Report format**: CSV download from dashboard button + `GET /reports/detections` API both, or just one?