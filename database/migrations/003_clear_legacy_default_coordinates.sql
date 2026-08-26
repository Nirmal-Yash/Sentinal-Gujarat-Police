-- Legacy catalogue rows inherited this former application default despite the
-- live source providing no coordinates.  A shared placeholder is not GIS data:
-- make the missing location explicit until a registry import/manual update
-- provides a verified point.
UPDATE cameras
SET lat = NULL, lng = NULL, geom = NULL, updated_at = NOW()
WHERE lat = 22.3039 AND lng = 70.8022;
