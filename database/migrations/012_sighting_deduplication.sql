-- Prevent repeated business sightings for the same normalized plate/camera
-- inside the same short observation bucket while retaining legitimate later sightings.
ALTER TABLE vehicle_sightings ADD COLUMN IF NOT EXISTS observation_bucket TIMESTAMPTZ;
UPDATE vehicle_sightings
SET observation_bucket = date_bin(INTERVAL '30 seconds', source_timestamp, TIMESTAMPTZ '1970-01-01')
WHERE observation_bucket IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_sighting_business_window
ON vehicle_sightings(camera_id, normalized_plate, observation_bucket)
WHERE camera_id IS NOT NULL AND normalized_plate IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_vehicle_sightings_business_lookup
ON vehicle_sightings(normalized_plate, camera_id, source_timestamp DESC);
