# Sentinel Refactor Verification Manifest

Release acceptance is based on the agreed M0-M10 plan.

- Core pipeline: canonical event -> vehicle detection -> tracking -> adaptive ANPR -> confirmed sighting -> persistence.
- Business separation: detections/tracks are high-volume analytics; sightings/journeys/alerts are durable business records.
- ANPR: continuous sampled detection/tracking; adaptive OCR; explicit validation and consensus; only confirmed plates reach watchlists/journeys.
- Journey: plate-confirmed identity is authoritative; ordered source-time sightings form the route.
- Alerts: NEW -> ACKNOWLEDGED -> INVESTIGATING -> RESOLVED -> CLOSED, authenticated actor and audit trail.
- Registry/GIS: PostGIS canonical camera geometry and provenance; estimated radius is explicitly non-authoritative.
- Operations: stream health and AI health are separate concerns; runtime telemetry is persisted.
- Security: permission-based RBAC, mandatory production secret, no committed .env or Python bytecode.
- Verification: deterministic ANPR tests, persistence E2E, evidence regression, 50-camera registry smoke, migration idempotency, Compose validation, dashboard build.

Real-world accuracy and heterogeneous Government-feed acceptance require representative labelled footage and reachable production sources; CI must never fabricate those measurements.
