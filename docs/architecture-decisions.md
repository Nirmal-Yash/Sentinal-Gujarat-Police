# Architecture decision and extension-point register

This register applies the conditional-enhancement directive to the current
Docker Compose PoC.  It does not authorize speculative infrastructure.  The
existing boundaries—Dashboard, API/Registry, Ingestion, AI, Intelligence,
PostgreSQL/PostGIS and Redis Streams—remain the supported deployment model.

## Decisions already implemented

The following recommendations have a direct, low-risk benefit and are already
implemented: the canonical PostGIS registry; manual and CSV onboarding with
import/audit history; opt-in JWT/RBAC (including WebSockets) and isolated
synthetic diagnostics; normalized vendor/model management; observed stream metadata; indexed registry/plate search;
durable vehicle sightings; restart-safe alert deduplication; stable compact
Gujarat GIS; camera clustering/layers; persistent UI preferences; selectable
camera and journey routes; and Redis event envelopes.

## Deferred or rejected recommendations

Each item below retains a concrete seam.  A deferred item may be implemented
only when its trigger is measured or its required external authority/data is
available.  A rejected item is not part of the current roadmap; its seam
prevents a later valid need from requiring a rewrite.

| Recommendation | Decision | Trigger to revisit | Explicit extension point retained now |
| --- | --- | --- | --- |
| XLSX bulk onboarding | Defer | Approved parser dependency and a sample departmental workbook | CSV onboarding/import history is implemented at `POST /cameras/imports/csv`; `CameraCreate`, `camera_imports`, `cameras`, and `camera_audit_log` form the validated import boundary. |
| Automatic geocoding of camera locations | Defer | An approved government geocoder/dataset, coordinate policy and rate limit | `coord_source` and `coord_confidence` preserve provenance; manual onboarding and CSV imports accept verified coordinates, and `cameras.geom` is the single GIS projection. No guessed Gujarat locations are stored. |
| Duplicate-camera resolution | Defer | Source identifiers and departmental duplicate policy are supplied | Canonical UUID plus unique `stream_id`; duplicate matching belongs in a future import-review service, never the dashboard. |
| ONVIF, HLS/WHEP, vendor-VMS discovery | Defer | Approved credentials, vendor interface, and test feed | `ingestion/stream_adapters.py` defines `StreamAdapter` and `adapter_for`; `OpenCVRTSPAdapter` preserves current RTSP behavior. |
| PTZ, night vision and device capabilities | Defer | A source/VMS reports trustworthy capabilities | Registry `analytics_capabilities` JSON and `camera_type` are the canonical metadata seam; add typed capability fields only once source semantics are known. |
| Historical health measurements, bitrate and lag metrics | Defer | Retention, sampling cadence and operational thresholds are defined | Current `observed_*`, `last_frame_at`, reconnect and decode-failure fields are the latest-state boundary. Add an append-only `camera_health_observations` table behind this same projection. |
| Monitoring-gap/geofence analytics | Defer | Authoritative zones, coverage geometry and policy are supplied | Map has a dedicated coverage layer group; PostGIS `cameras.geom` is spatial authority. Do not infer policing gaps from camera circles. |
| Evidence viewer and formal investigation report template | Defer | Evidence retention/access rules and report template are approved | `/reports/detections` already provides the shared JSON/CSV query; the vehicle journey map route is implemented from `/search/track/{id}`; `vehicle_sightings.evidence_id` is ready for an evidence store. |
| Multi-frame ANPR consensus | Defer | Camera cadence and accuracy thresholds are measured on real feeds | ANPR emits stable `event_id`, normalized plate, OCR/detector confidence and local track ID. A consensus component can consume these event fields without changing ingestion. |
| Generic analytics-event, vehicle-track and journey tables | Defer | A consumer needs a generic query model beyond detections/sightings | Versioned event envelope (`schema_version`, `event_id`, `event_type`, camera/stream/time fields) and `detections.metadata` preserve the future mapping seam. |
| Object-storage evidence, signed links and video retention tiers | Defer | Approved retention policy and object-storage authority | `vehicle_sightings.evidence_id` and alert `details` provide opaque references; no binary evidence is placed in PostgreSQL. |
| Kafka/Redpanda, external search engine, TimescaleDB | Defer | Measured Redis throughput/replay, partitioning or historical-query limits | Producers/consumers communicate through named versioned events; PostgreSQL indexes cover current search. Introduce a broker adapter at the event-publisher/consumer boundary, not in UI or business records. |
| Kubernetes, service mesh, API gateway/WAF | Reject for PoC | Reconsider only for multi-node operations, approved network policy or managed ingress | Docker Compose service boundaries and FastAPI route boundary remain stable; no application code assumes a single UI component owns backend logic. |
| Microservice decomposition | Reject for PoC | Independent scaling, release cadence or security isolation is measured | Current logical services are independently deployable containers; extract only an existing responsibility, retaining the event/API contract. |
| Database replication, sharding and regional edge nodes | Defer | Regional latency, camera count, RPO/RTO and bandwidth targets are accepted | Canonical UUIDs, PostGIS geometry, stateless API reads and event envelopes avoid dependence on process-local identity. |
| Dead-letter streams, outbox and distributed transactions | Defer | Measured malformed/retry rate or a durable external delivery requirement | Stable event IDs, idempotent sighting inserts and alert deduplication are already in place. Add `<stream>.dlq` consumers and an outbox only with retry/retention policy. |
| External OIDC/tenant isolation | Defer | Identity provider, role matrix and legal data-access policy are approved | The opt-in JWT/RBAC boundary covers HTTP and WebSockets now; `users`/`user_sessions` and role dependencies can be replaced with an approved OIDC adapter without changing UI authorization semantics. |
| VAHAN/SARTHI/eGujCop/AFIS/NAFIS connectors | Defer | Written authorization and interface contracts | `source_system`, canonical registry IDs and versioned events are integration keys. A connector must be a backend adapter with audit/rate-limit behavior, never a frontend direct call. |
| Central metrics/tracing stack | Defer | Monitoring backend and SLOs are selected | Existing structured service logs and the health endpoint remain the initial probes. Correlation/event IDs are propagated for future trace context. |
| GPU acceleration and horizontal AI workers | Defer | CPU/GPU saturation and per-camera inference latency are measured | Existing `YOLO_WORKERS` and process supervision are configurable; preserve event contracts if moving workers to GPU/edge nodes. |

## Rules for future implementation

1. Implement only through the listed seam, preserving canonical camera UUIDs,
   PostGIS geometry and versioned event fields.
2. Add migrations, rollback notes, contract tests and measured acceptance data
   before enabling a deferred capability.
3. Treat external credentials, identity providers, evidence stores and
   government datasets as integrations requiring authorization—not placeholders.
4. Do not add infrastructure solely to satisfy this register. A trigger must be
   demonstrable in the evaluation or operational environment.
