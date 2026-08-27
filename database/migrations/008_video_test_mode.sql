-- Video-backed test mode is isolated from the operational schema.  No table
-- below has a foreign key to a production camera, detection, alert or track.
ALTER TABLE test_sessions ADD COLUMN IF NOT EXISTS loop BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE test_sessions ADD COLUMN IF NOT EXISTS frames_processed BIGINT NOT NULL DEFAULT 0;
ALTER TABLE test_sessions ADD COLUMN IF NOT EXISTS runner_pid INTEGER;
ALTER TABLE test_sessions ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE test_sessions ADD COLUMN IF NOT EXISTS error TEXT;

ALTER TABLE test_detections ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE test_detections ADD COLUMN IF NOT EXISTS stream_id INTEGER;
ALTER TABLE test_detections ADD COLUMN IF NOT EXISTS source_timestamp TIMESTAMPTZ;
ALTER TABLE test_detections ADD COLUMN IF NOT EXISTS track_id VARCHAR(255);
ALTER TABLE test_detections ADD COLUMN IF NOT EXISTS bbox JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE test_alerts ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE test_alerts ADD COLUMN IF NOT EXISTS acknowledged BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE test_alerts ADD COLUMN IF NOT EXISTS event_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS test_tracks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    global_track_id VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    first_camera_label VARCHAR(255),
    last_camera_label VARCHAR(255),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sightings JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_test BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(session_id, global_track_id)
);

CREATE TABLE IF NOT EXISTS test_video_assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    storage_key VARCHAR(512) NOT NULL UNIQUE,
    display_name VARCHAR(512) NOT NULL,
    source_kind VARCHAR(16) NOT NULL CHECK (source_kind IN ('bundled','upload')),
    width INTEGER, height INTEGER, fps DOUBLE PRECISION, duration_seconds DOUBLE PRECISION,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_test BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS test_session_feeds (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES test_video_assets(id) ON DELETE RESTRICT,
    stream_id INTEGER NOT NULL,
    camera_label VARCHAR(255) NOT NULL,
    rtsp_path VARCHAR(512) NOT NULL,
    hls_path VARCHAR(512) NOT NULL,
    loop BOOLEAN NOT NULL DEFAULT TRUE,
    width INTEGER, height INTEGER, fps DOUBLE PRECISION,
    is_test BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(session_id, stream_id)
);

ALTER TABLE test_session_feeds ADD COLUMN IF NOT EXISTS loop BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_test_tracks_session_recent ON test_tracks(session_id, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_feeds_session ON test_session_feeds(session_id, stream_id);
