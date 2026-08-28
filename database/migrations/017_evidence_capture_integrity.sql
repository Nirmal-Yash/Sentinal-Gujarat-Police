-- Evidence produced by the alert pipeline is immutable metadata referencing an
-- object in the shared evidence volume. Prevent accidental duplicate links.
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_alert_storage
    ON evidence(alert_id, storage_key)
    WHERE alert_id IS NOT NULL AND storage_key IS NOT NULL;

ALTER TABLE evidence DROP CONSTRAINT IF EXISTS evidence_media_type_check;
ALTER TABLE evidence ADD CONSTRAINT evidence_media_type_check
    CHECK (media_type IN ('image/jpeg','image/png','video/mp4','application/json'));
