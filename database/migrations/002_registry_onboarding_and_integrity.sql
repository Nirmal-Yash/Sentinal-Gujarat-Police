-- Model-1 registry refinement. Safe for databases that already ran migration 001.
ALTER TABLE cameras ALTER COLUMN rtsp_url DROP NOT NULL;
ALTER TABLE cameras ALTER COLUMN lat DROP DEFAULT;
ALTER TABLE cameras ALTER COLUMN lng DROP DEFAULT;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS external_id VARCHAR(255);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS installation_date DATE;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS ptz_capable BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS night_vision_capable BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_cameras_external_source
  ON cameras(source_system, external_id) WHERE external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS camera_imports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(512) NOT NULL,
    source_system VARCHAR(255) NOT NULL DEFAULT 'csv',
    actor VARCHAR(255) NOT NULL DEFAULT 'api',
    total_rows INTEGER NOT NULL DEFAULT 0,
    accepted_rows INTEGER NOT NULL DEFAULT 0,
    rejected_rows INTEGER NOT NULL DEFAULT 0,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Invalid/missing coordinates remain explicit. A separate validation process is
-- required before correcting imported geography; no default point is generated.
ALTER TABLE cameras DROP CONSTRAINT IF EXISTS cameras_coordinates_valid;
ALTER TABLE cameras ADD CONSTRAINT cameras_coordinates_valid CHECK (
    (lat IS NULL AND lng IS NULL) OR
    (lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180 AND NOT (lat = 0 AND lng = 0))
);
