-- Session-scoped Test Mode watchlist; never reads/writes production watchlist.
CREATE TABLE IF NOT EXISTS test_watchlist (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL DEFAULT 'person',
    description TEXT NOT NULL DEFAULT '',
    plate_number VARCHAR(50),
    embedding vector(512),
    alert_priority VARCHAR(20) NOT NULL DEFAULT 'HIGH',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_test_watchlist_session_active ON test_watchlist(session_id,is_active,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_watchlist_session_plate ON test_watchlist(session_id,plate_number);
CREATE INDEX IF NOT EXISTS idx_test_watchlist_session_embedding ON test_watchlist(session_id);
