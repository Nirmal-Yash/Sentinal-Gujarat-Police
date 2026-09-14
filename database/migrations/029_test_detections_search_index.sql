-- Migration 029: test_detections search index and evidence test lookup index

CREATE INDEX IF NOT EXISTS idx_test_detections_session_plate
    ON test_detections(session_id, event_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_test_detection
    ON evidence((metadata->>'detection_id'))
    WHERE (metadata->>'test')::boolean = TRUE;

CREATE INDEX IF NOT EXISTS idx_evidence_metadata_alert_id
    ON evidence((metadata->>'alert_id'))
    WHERE metadata->>'alert_id' IS NOT NULL;
