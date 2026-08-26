-- Additive migration for existing Sentinel deployments.  New installations
-- receive the same schema through init.sql.  Run once with:
-- docker compose exec -T postgres psql -U sentinel -d sentinel -f /migrations/001_model1_registry.sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE cameras ADD COLUMN IF NOT EXISTS department VARCHAR(255) NOT NULL DEFAULT 'Unassigned';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS owner_organization VARCHAR(255) NOT NULL DEFAULT 'Unassigned';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS camera_type VARCHAR(100) NOT NULL DEFAULT 'fixed';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS connectivity_status VARCHAR(50) NOT NULL DEFAULT 'unknown';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS protocol VARCHAR(32) NOT NULL DEFAULT 'rtsp';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS source_system VARCHAR(255) DEFAULT '';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS storage_type VARCHAR(100) DEFAULT '';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS retention_days INTEGER;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS analytics_capabilities JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS maintenance_status VARCHAR(50) NOT NULL DEFAULT 'unknown';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS maintenance_due_at TIMESTAMPTZ;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS observed_codec VARCHAR(64);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS observed_width INTEGER;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS observed_height INTEGER;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS observed_fps DOUBLE PRECISION;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS observed_at TIMESTAMPTZ;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS health_status VARCHAR(50) NOT NULL DEFAULT 'unknown';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS last_frame_at TIMESTAMPTZ;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS reconnect_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS decode_failure_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS dedup_key VARCHAR(512);
ALTER TABLE cameras ALTER COLUMN codec DROP DEFAULT;
ALTER TABLE cameras ALTER COLUMN width DROP DEFAULT;
ALTER TABLE cameras ALTER COLUMN height DROP DEFAULT;
ALTER TABLE cameras ALTER COLUMN fps DROP DEFAULT;
ALTER TABLE cameras ALTER COLUMN lat DROP DEFAULT;
ALTER TABLE cameras ALTER COLUMN lng DROP DEFAULT;
-- Legacy builds populated these defaults even when no probe/catalogue supplied
-- them. Clear unobserved values so the API reports N/A until a validated
-- configuration or runtime observation arrives.
UPDATE cameras SET codec=NULL, width=NULL, height=NULL, fps=NULL
WHERE observed_at IS NULL;
UPDATE cameras SET geom = ST_SetSRID(ST_MakePoint(lng, lat), 4326) WHERE geom IS NULL;
CREATE OR REPLACE FUNCTION cameras_sync_geometry() RETURNS trigger AS $$
BEGIN
  NEW.geom := ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS cameras_geometry_from_coordinates ON cameras;
CREATE TRIGGER cameras_geometry_from_coordinates
  BEFORE INSERT OR UPDATE OF lat, lng ON cameras
  FOR EACH ROW EXECUTE FUNCTION cameras_sync_geometry();

CREATE TABLE IF NOT EXISTS camera_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), camera_id UUID REFERENCES cameras(id),
    actor VARCHAR(255) NOT NULL DEFAULT 'system', action VARCHAR(64) NOT NULL,
    before_value JSONB, after_value JSONB, correlation_id UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS vehicle_sightings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), event_id UUID NOT NULL UNIQUE,
    detection_id UUID REFERENCES detections(id) ON DELETE SET NULL, raw_plate VARCHAR(100),
    normalized_plate VARCHAR(100) NOT NULL, camera_id UUID REFERENCES cameras(id) ON DELETE SET NULL,
    source_timestamp TIMESTAMPTZ NOT NULL, confidence DOUBLE PRECISION NOT NULL,
    vehicle_type VARCHAR(50), track_id VARCHAR(255), global_vehicle_id VARCHAR(255),
    evidence_id VARCHAR(255), model_versions JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cameras_geom ON cameras USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_cameras_name_trgm ON cameras USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_cameras_location_trgm ON cameras USING GIN (location gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_cameras_department_trgm ON cameras USING GIN (department gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_cameras_filter ON cameras(status, health_status, department, camera_type);
CREATE INDEX IF NOT EXISTS idx_sightings_plate_ts ON vehicle_sightings(normalized_plate, source_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_sightings_camera_ts ON vehicle_sightings(camera_id, source_timestamp DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_dedup_key ON alerts(dedup_key) WHERE dedup_key IS NOT NULL;
