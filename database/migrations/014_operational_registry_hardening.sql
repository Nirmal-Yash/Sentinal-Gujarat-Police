-- Operational registry hardening: explicit provenance ranks and bounded health history.
ALTER TABLE cameras
  ADD COLUMN IF NOT EXISTS coord_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS coord_verified_by VARCHAR(255),
  ADD COLUMN IF NOT EXISTS metadata_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS metadata_verified_by VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_cameras_coord_quality
  ON cameras(coord_source, coord_confidence DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_cameras_health_status
  ON cameras(health_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_obs_camera_status_time
  ON camera_health_observations(camera_id, health_status, observed_at DESC);

-- Keep one operational observation per camera/time bucket when workers retry a health write.
ALTER TABLE camera_health_observations
  ADD COLUMN IF NOT EXISTS observation_bucket TIMESTAMPTZ;

UPDATE camera_health_observations
SET observation_bucket = date_trunc('minute', observed_at)
WHERE observation_bucket IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_camera_health_observation_bucket
  ON camera_health_observations(camera_id, observation_bucket);

-- Registry source states used by reconciliation/administration.
UPDATE cameras SET coord_source='unknown' WHERE coord_source IS NULL OR trim(coord_source)='';
UPDATE cameras SET department_source='unknown' WHERE department_source IS NULL OR trim(department_source)='';
