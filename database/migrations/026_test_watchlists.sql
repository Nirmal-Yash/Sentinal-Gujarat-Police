CREATE TABLE IF NOT EXISTS test_watchlists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL CHECK (entity_type IN ('person','vehicle')),
    description TEXT NOT NULL DEFAULT '',
    plate_number VARCHAR(50),
    embedding VECTOR(512),
    alert_priority VARCHAR(20) NOT NULL DEFAULT 'HIGH',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_test BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_test_watchlists_session_active ON test_watchlists(session_id,is_active,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_watchlists_plate ON test_watchlists(session_id,plate_number) WHERE is_active=TRUE;
CREATE INDEX IF NOT EXISTS idx_test_watchlists_embedding ON test_watchlists USING ivfflat (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;
