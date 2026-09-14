-- Migration 028: Audit tables, performance indexes, and backward-compatible views
CREATE TABLE IF NOT EXISTS test_vehicle_sightings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    camera_id UUID,
    stream_id INT,
    plate_text VARCHAR(100) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_test_sightings_session_plate ON test_vehicle_sightings(session_id, plate_text);

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,
    user_id UUID,
    username VARCHAR(255),
    ip_address VARCHAR(45),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type);

CREATE TABLE IF NOT EXISTS face_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id UUID,
    session_id UUID,
    embedding vector(512),
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_face_obs_camera_time ON face_observations(camera_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_face_obs_session ON face_observations(session_id) WHERE session_id IS NOT NULL;

ALTER TABLE vehicle_sightings ADD COLUMN IF NOT EXISTS plate_text VARCHAR(100) GENERATED ALWAYS AS (COALESCE(normalized_plate, raw_plate, '')) STORED;
ALTER TABLE vehicle_sightings ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ GENERATED ALWAYS AS (source_timestamp) STORED;
ALTER TABLE vehicle_sightings ADD COLUMN IF NOT EXISTS session_id UUID;

CREATE INDEX IF NOT EXISTS idx_sightings_plate_time ON vehicle_sightings(plate_text, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_sightings_camera_time ON vehicle_sightings(camera_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_sightings_session ON vehicle_sightings(session_id) WHERE session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_alerts_status_time ON alerts(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_camera_time ON alerts(cam_id, created_at DESC);

ALTER TABLE cameras ADD COLUMN IF NOT EXISTS active BOOLEAN GENERATED ALWAYS AS (status = 'active') STORED;
CREATE INDEX IF NOT EXISTS idx_cameras_external_id ON cameras(external_id);
CREATE INDEX IF NOT EXISTS idx_cameras_health_status ON cameras(health_status);
CREATE INDEX IF NOT EXISTS idx_cameras_active ON cameras(active);

CREATE OR REPLACE VIEW watchlist_entries AS
    SELECT id, name, entity_type, description, plate_number, alert_priority, is_active AS active, created_at
    FROM watchlist;

CREATE INDEX IF NOT EXISTS idx_watchlist_active ON watchlist(is_active);
CREATE INDEX IF NOT EXISTS idx_watchlist_plate ON watchlist(plate_number);
