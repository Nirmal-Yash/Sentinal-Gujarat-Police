-- Test/performance and registry compatibility hardening.
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS processing_fps_category VARCHAR(32);
UPDATE cameras SET processing_fps_category='pedestrian' WHERE processing_fps_category IS NULL;
ALTER TABLE cameras ALTER COLUMN processing_fps_category SET DEFAULT 'pedestrian';
ALTER TABLE cameras ALTER COLUMN processing_fps_category SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_test_detections_session_event ON test_detections(session_id,event_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_alerts_session_event ON test_alerts(session_id,event_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_feeds_session_stream ON test_session_feeds(session_id,stream_id);
