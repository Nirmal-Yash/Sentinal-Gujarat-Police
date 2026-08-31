-- P1 intelligence consistency: isolated test embeddings, canonical watchlist lookup support.
ALTER TABLE test_tracks
    ADD COLUMN IF NOT EXISTS embedding vector(512);

CREATE INDEX IF NOT EXISTS idx_test_tracks_session_embedding
    ON test_tracks(session_id);

CREATE INDEX IF NOT EXISTS idx_watchlist_active_normalized_plate
    ON watchlist ((regexp_replace(upper(COALESCE(plate_number,'')),'[^A-Z0-9]','','g')))
    WHERE is_active = TRUE AND plate_number IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_test_detections_session_plate
    ON test_detections(session_id, plate_text, event_at DESC);

-- Record the normalization contract used by P1 components.
CREATE TABLE IF NOT EXISTS intelligence_contracts (
    name VARCHAR(100) PRIMARY KEY,
    version VARCHAR(32) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO intelligence_contracts(name, version)
VALUES ('plate_normalization', '1.1')
ON CONFLICT (name) DO UPDATE SET version=EXCLUDED.version, updated_at=NOW();
