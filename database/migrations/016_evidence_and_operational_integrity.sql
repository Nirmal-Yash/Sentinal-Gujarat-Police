-- Evidence must be auditable independently of alert lifecycle history.
CREATE TABLE IF NOT EXISTS evidence_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    evidence_id UUID NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
    actor VARCHAR(255) NOT NULL,
    action VARCHAR(64) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_evidence_audit_evidence_created
    ON evidence_audit_log(evidence_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_camera_health_camera_observed
    ON camera_health_observations(camera_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_detections_cam_timestamp
    ON detections(cam_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_vehicle_sightings_source_timestamp
    ON vehicle_sightings(source_timestamp DESC);

ALTER TABLE evidence DROP CONSTRAINT IF EXISTS evidence_sha256_hex_check;
ALTER TABLE evidence ADD CONSTRAINT evidence_sha256_hex_check
    CHECK (sha256 IS NULL OR sha256 ~ '^[0-9A-Fa-f]{64}$');

ALTER TABLE camera_health_observations DROP CONSTRAINT IF EXISTS health_rates_nonnegative;
ALTER TABLE camera_health_observations ADD CONSTRAINT health_rates_nonnegative
    CHECK (
        (source_fps IS NULL OR source_fps >= 0) AND
        (decode_fps IS NULL OR decode_fps >= 0) AND
        (published_fps IS NULL OR published_fps >= 0) AND
        reconnect_count >= 0 AND
        decode_failure_count >= 0
    );
