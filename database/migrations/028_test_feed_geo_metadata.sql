-- Isolated GIS metadata for Test Mode camera slots.
ALTER TABLE test_session_feeds ADD COLUMN IF NOT EXISTS location VARCHAR(255);
ALTER TABLE test_session_feeds ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
ALTER TABLE test_session_feeds ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;
CREATE INDEX IF NOT EXISTS idx_test_feeds_session_geo ON test_session_feeds(session_id,lat,lng);
