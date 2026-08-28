-- Runtime integrity for track-driven ANPR business sightings.
-- The application already uses this bucket for deterministic duplicate
-- suppression; make the schema explicit before creating the unique index.
ALTER TABLE vehicle_sightings
    ADD COLUMN IF NOT EXISTS observation_bucket TIMESTAMPTZ;

UPDATE vehicle_sightings
SET observation_bucket = date_trunc('minute', source_timestamp)
                         - make_interval(secs => (extract(second FROM source_timestamp)::integer % 30))
WHERE observation_bucket IS NULL;

CREATE INDEX IF NOT EXISTS idx_sightings_bucket
    ON vehicle_sightings(camera_id, normalized_plate, observation_bucket);

-- Preserve the strongest existing observation if older test/runtime data
-- contains duplicates created before database-level suppression existed.
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
             PARTITION BY camera_id, normalized_plate, observation_bucket
             ORDER BY confidence DESC NULLS LAST, created_at DESC, id
           ) AS rn
    FROM vehicle_sightings
    WHERE camera_id IS NOT NULL
      AND normalized_plate IS NOT NULL
      AND observation_bucket IS NOT NULL
)
DELETE FROM vehicle_sightings s
USING ranked r
WHERE s.id = r.id AND r.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_sighting_camera_plate_bucket
    ON vehicle_sightings(camera_id, normalized_plate, observation_bucket)
    WHERE camera_id IS NOT NULL AND normalized_plate IS NOT NULL AND observation_bucket IS NOT NULL;

ALTER TABLE vehicle_sightings
    ALTER COLUMN observation_bucket SET NOT NULL;

-- Explicitly constrain operational states used by the alert state machine.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'alerts_status_check') THEN
        ALTER TABLE alerts ADD CONSTRAINT alerts_status_check
          CHECK (status IN ('NEW','ACKNOWLEDGED','INVESTIGATING','RESOLVED','CLOSED'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'vehicle_journeys_status_check') THEN
        ALTER TABLE vehicle_journeys ADD CONSTRAINT vehicle_journeys_status_check
          CHECK (status IN ('ACTIVE','COMPLETED','CANCELLED'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_vehicle_journey_sightings_sighting
    ON vehicle_journey_sightings(sighting_id);
