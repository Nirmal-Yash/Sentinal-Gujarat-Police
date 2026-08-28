-- Ensure health writes are bucketed even when workers omit the bucket explicitly.
ALTER TABLE camera_health_observations
  ALTER COLUMN observation_bucket SET DEFAULT date_trunc('minute', NOW());

-- Historical observations are append-oriented and must always carry a timestamp.
ALTER TABLE camera_health_observations
  ALTER COLUMN observed_at SET DEFAULT NOW();
