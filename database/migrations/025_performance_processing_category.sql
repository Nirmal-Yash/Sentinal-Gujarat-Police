ALTER TABLE cameras ADD COLUMN IF NOT EXISTS processing_fps_category VARCHAR(32) NOT NULL DEFAULT 'pedestrian';

UPDATE cameras
SET processing_fps_category = CASE
  WHEN lower(coalesce(name,'') || ' ' || coalesce(location,'')) ~ '(highway|expressway|ring road|flyover)' THEN 'highway'
  WHEN lower(coalesce(name,'') || ' ' || coalesce(location,'')) ~ '(parking|entrance|office|building)' THEN 'static'
  ELSE 'pedestrian'
END
WHERE processing_fps_category IS NULL
   OR processing_fps_category NOT IN ('highway','pedestrian','static');

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname='cameras_processing_fps_category_check'
  ) THEN
    ALTER TABLE cameras
      ADD CONSTRAINT cameras_processing_fps_category_check
      CHECK (processing_fps_category IN ('highway','pedestrian','static'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_cameras_processing_fps_category
  ON cameras(processing_fps_category);
