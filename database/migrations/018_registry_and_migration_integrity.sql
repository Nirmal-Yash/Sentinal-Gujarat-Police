-- Migration continuity and registry integrity hardening.
-- The 012 sighting deduplication logic is consolidated into 012_runtime_integrity_and_dedup;
-- this migration adds safety constraints/indexes without relying on duplicate migration numbers.
ALTER TABLE cameras
  ADD COLUMN IF NOT EXISTS metadata_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS metadata_verified_by VARCHAR(128),
  ADD COLUMN IF NOT EXISTS registry_version BIGINT NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_cameras_coord_review
  ON cameras(coord_source, coord_confidence);
CREATE INDEX IF NOT EXISTS idx_cameras_department_health
  ON cameras(department, health_status);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'vehicle_sighting_confidence_check') THEN
    ALTER TABLE vehicle_sightings ADD CONSTRAINT vehicle_sighting_confidence_check
      CHECK (confidence >= 0 AND confidence <= 1);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS migration_integrity_marker (
  id BOOLEAN PRIMARY KEY DEFAULT TRUE,
  checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO migration_integrity_marker(id) VALUES(TRUE)
ON CONFLICT (id) DO UPDATE SET checked_at=NOW();
