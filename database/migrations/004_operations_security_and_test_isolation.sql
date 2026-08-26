-- Operational extensions: all additions are isolated, auditable and reversible.
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS coord_source VARCHAR(32) NOT NULL DEFAULT 'unknown';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS coord_confidence DOUBLE PRECISION;
ALTER TABLE camera_imports ADD COLUMN IF NOT EXISTS status VARCHAR(24) NOT NULL DEFAULT 'completed';
ALTER TABLE camera_imports ADD COLUMN IF NOT EXISTS column_map JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(128) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(24) NOT NULL CHECK (role IN ('SUPERADMIN','ADMIN','OPERATOR','VIEWER')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti UUID NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_active ON user_sessions(user_id, expires_at) WHERE revoked = FALSE;

-- Test data has no FK to production entities by design.  A session identifier
-- is the only linkage within the test namespace.
CREATE TABLE IF NOT EXISTS test_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    created_by VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS test_detections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    camera_label VARCHAR(255) NOT NULL,
    detection_type VARCHAR(50) NOT NULL,
    plate_text VARCHAR(100), confidence DOUBLE PRECISION,
    event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS test_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    detection_id UUID REFERENCES test_detections(id) ON DELETE SET NULL,
    alert_type VARCHAR(100) NOT NULL, priority VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_test_detections_session_time ON test_detections(session_id, event_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_alerts_session_time ON test_alerts(session_id, created_at DESC);
