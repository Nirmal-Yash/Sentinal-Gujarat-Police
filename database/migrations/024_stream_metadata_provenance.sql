-- Distinguish source/catalogue metadata from runtime-observed stream metadata.
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS provided_fps DOUBLE PRECISION;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS provided_width INTEGER;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS provided_height INTEGER;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS provided_codec VARCHAR(64);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS metadata_conflict BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS metadata_conflict_at TIMESTAMPTZ;

UPDATE cameras SET provided_fps=fps WHERE provided_fps IS NULL AND fps IS NOT NULL;
UPDATE cameras SET provided_width=width WHERE provided_width IS NULL AND width IS NOT NULL;
UPDATE cameras SET provided_height=height WHERE provided_height IS NULL AND height IS NOT NULL;
UPDATE cameras SET provided_codec=codec WHERE provided_codec IS NULL AND codec IS NOT NULL;

CREATE OR REPLACE FUNCTION cameras_update_metadata_conflict() RETURNS trigger AS $$
BEGIN
  NEW.metadata_conflict := FALSE;
  IF NEW.provided_fps IS NOT NULL AND NEW.observed_fps IS NOT NULL AND abs(NEW.provided_fps - NEW.observed_fps) > GREATEST(1.0, NEW.provided_fps * 0.10) THEN NEW.metadata_conflict := TRUE; END IF;
  IF NEW.provided_width IS NOT NULL AND NEW.observed_width IS NOT NULL AND NEW.provided_width <> NEW.observed_width THEN NEW.metadata_conflict := TRUE; END IF;
  IF NEW.provided_height IS NOT NULL AND NEW.observed_height IS NOT NULL AND NEW.provided_height <> NEW.observed_height THEN NEW.metadata_conflict := TRUE; END IF;
  IF NEW.provided_codec IS NOT NULL AND NEW.observed_codec IS NOT NULL AND lower(NEW.provided_codec) <> lower(NEW.observed_codec) THEN NEW.metadata_conflict := TRUE; END IF;
  IF NEW.metadata_conflict THEN NEW.metadata_conflict_at := COALESCE(NEW.metadata_conflict_at, NOW()); ELSE NEW.metadata_conflict_at := NULL; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS cameras_metadata_conflict ON cameras;
CREATE TRIGGER cameras_metadata_conflict BEFORE INSERT OR UPDATE OF provided_fps,provided_width,provided_height,provided_codec,observed_fps,observed_width,observed_height,observed_codec ON cameras FOR EACH ROW EXECUTE FUNCTION cameras_update_metadata_conflict();
CREATE INDEX IF NOT EXISTS idx_cameras_metadata_conflict ON cameras(metadata_conflict) WHERE metadata_conflict=TRUE;
