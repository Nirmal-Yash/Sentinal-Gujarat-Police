-- Durable identity state and honest processing metadata.
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS observed_source_fps DOUBLE PRECISION;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS observed_decode_fps DOUBLE PRECISION;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS observed_published_fps DOUBLE PRECISION;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS department_source VARCHAR(32) NOT NULL DEFAULT 'unknown';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS department_confidence DOUBLE PRECISION;
UPDATE cameras SET department_source='government_seed', department_confidence=0.70
WHERE department <> 'Unassigned' AND department_source='unknown';

ALTER TABLE global_tracks ADD COLUMN IF NOT EXISTS identity_source VARCHAR(64) NOT NULL DEFAULT 'unknown';
ALTER TABLE global_tracks ADD COLUMN IF NOT EXISTS last_confidence DOUBLE PRECISION;
ALTER TABLE global_tracks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_global_tracks_entity_recent ON global_tracks(entity_type, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS camera_health_observations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    health_status VARCHAR(50) NOT NULL,
    source_fps DOUBLE PRECISION, decode_fps DOUBLE PRECISION, published_fps DOUBLE PRECISION,
    reconnect_count INTEGER NOT NULL DEFAULT 0, decode_failure_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_camera_health_observations_recent ON camera_health_observations(camera_id, observed_at DESC);
