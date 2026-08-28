-- Operational integrity: constrain alert/journey state and protect evidence references.
UPDATE alerts SET status='NEW' WHERE status IS NULL OR status NOT IN ('NEW','ACKNOWLEDGED','INVESTIGATING','RESOLVED','CLOSED');
ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_status_check;
ALTER TABLE alerts ADD CONSTRAINT alerts_status_check CHECK (status IN ('NEW','ACKNOWLEDGED','INVESTIGATING','RESOLVED','CLOSED'));

UPDATE vehicle_journeys SET status='ACTIVE' WHERE status IS NULL OR status NOT IN ('ACTIVE','COMPLETED','FAILED','CANCELLED');
ALTER TABLE vehicle_journeys DROP CONSTRAINT IF EXISTS vehicle_journeys_status_check;
ALTER TABLE vehicle_journeys ADD CONSTRAINT vehicle_journeys_status_check CHECK (status IN ('ACTIVE','COMPLETED','FAILED','CANCELLED'));

CREATE INDEX IF NOT EXISTS idx_vehicle_sightings_journey_ts ON vehicle_sightings(journey_id, source_timestamp ASC);
CREATE INDEX IF NOT EXISTS idx_vehicle_sightings_plate_camera_ts ON vehicle_sightings(normalized_plate, camera_id, source_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_cam_created ON alerts(cam_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_camera_captured ON evidence(camera_id, captured_at DESC);

-- Keep evidence references discoverable and prevent malformed empty storage keys.
ALTER TABLE evidence DROP CONSTRAINT IF EXISTS evidence_storage_key_nonempty;
ALTER TABLE evidence ADD CONSTRAINT evidence_storage_key_nonempty CHECK (length(trim(storage_key)) > 0);
