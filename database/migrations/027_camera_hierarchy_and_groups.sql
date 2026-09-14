CREATE TABLE IF NOT EXISTS camera_groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(64) UNIQUE NOT NULL,
    parent_id UUID REFERENCES camera_groups(id) ON DELETE CASCADE,
    group_type VARCHAR(64) NOT NULL DEFAULT 'zone',
    description TEXT NOT NULL DEFAULT '',
    geom GEOMETRY(Geometry, 4326),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_camera_groups_parent ON camera_groups(parent_id);
CREATE INDEX IF NOT EXISTS idx_camera_groups_type ON camera_groups(group_type);
CREATE INDEX IF NOT EXISTS idx_camera_groups_geom ON camera_groups USING gist(geom);

ALTER TABLE cameras ADD COLUMN IF NOT EXISTS group_id UUID REFERENCES camera_groups(id) ON DELETE SET NULL;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS zone VARCHAR(128) NOT NULL DEFAULT 'Ahmedabad Zone';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS district VARCHAR(128) NOT NULL DEFAULT 'Ahmedabad';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS subdivision VARCHAR(128) NOT NULL DEFAULT 'City Division';
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS police_station VARCHAR(128) NOT NULL DEFAULT 'City Police Station';

CREATE INDEX IF NOT EXISTS idx_cameras_group_id ON cameras(group_id);
CREATE INDEX IF NOT EXISTS idx_cameras_zone_district ON cameras(zone, district);
CREATE INDEX IF NOT EXISTS idx_cameras_police_station ON cameras(police_station);

-- Seed core Gujarat Police administrative hierarchy
INSERT INTO camera_groups (id, name, code, parent_id, group_type, description)
VALUES 
  ('11111111-1111-1111-1111-111111110001', 'State Surveillance Command (DGP Office)', 'GUJ-HQ', NULL, 'state', 'Apex state command and coordination centre'),
  ('11111111-1111-1111-1111-111111110002', 'Ahmedabad City Police Zone', 'ZONE-AMD', '11111111-1111-1111-1111-111111110001', 'zone', 'Urban surveillance and integrated traffic corridor'),
  ('11111111-1111-1111-1111-111111110003', 'Gandhinagar Capital Range', 'ZONE-GNR', '11111111-1111-1111-1111-111111110001', 'zone', 'Capital city security and secretariat surveillance'),
  ('11111111-1111-1111-1111-111111110004', 'Surat City Police Zone', 'ZONE-SRT', '11111111-1111-1111-1111-111111110001', 'zone', 'South Gujarat industrial and smart city surveillance'),
  ('11111111-1111-1111-1111-111111110005', 'Rajkot Range', 'ZONE-RJK', '11111111-1111-1111-1111-111111110001', 'zone', 'Saurashtra regional urban and highway grid'),
  ('11111111-1111-1111-1111-111111110006', 'Vadodara Range', 'ZONE-BDQ', '11111111-1111-1111-1111-111111110001', 'zone', 'Central Gujarat commercial and transit hub'),
  ('11111111-1111-1111-1111-111111110007', 'Coastal & Border Security Range', 'ZONE-CST', '11111111-1111-1111-1111-111111110001', 'zone', 'Port security, maritime access roads, and frontier checkpoints'),
  ('11111111-1111-1111-1111-111111110008', 'State Highway Patrol Corridor', 'CORR-HWY', '11111111-1111-1111-1111-111111110001', 'corridor', 'High speed ANPR toll gates and national highway intersections'),

  -- Divisions and Police Stations under Ahmedabad
  ('11111111-1111-1111-1111-111111110010', 'SG Highway Traffic Division', 'DIV-SGH', '11111111-1111-1111-1111-111111110002', 'division', 'SG Highway arterial traffic and rapid transit surveillance'),
  ('11111111-1111-1111-1111-111111110011', 'Kalupur Police Station', 'PS-KLP', '11111111-1111-1111-1111-111111110002', 'police_station', 'Kalupur central station and historic market jurisdiction'),
  ('11111111-1111-1111-1111-111111110012', 'Naroda Police Station', 'PS-NRD', '11111111-1111-1111-1111-111111110002', 'police_station', 'Naroda industrial estate and ring road junction'),
  ('11111111-1111-1111-1111-111111110013', 'Bapunagar Police Station', 'PS-BPN', '11111111-1111-1111-1111-111111110002', 'police_station', 'East Ahmedabad residential and diamond market zone'),
  ('11111111-1111-1111-1111-111111110014', 'SP Ring Road Traffic Unit', 'DIV-SPR', '11111111-1111-1111-1111-111111110002', 'division', 'Sardar Patel peripheral ring road toll and bypass control'),
  ('11111111-1111-1111-1111-111111110015', 'Maninagar Police Station', 'PS-MNN', '11111111-1111-1111-1111-111111110002', 'police_station', 'South Ahmedabad transit terminal and urban zone'),
  ('11111111-1111-1111-1111-111111110016', 'Ellisbridge Police Station', 'PS-ELB', '11111111-1111-1111-1111-111111110002', 'police_station', 'Ashram Road riverfront and civic institutional sector')
ON CONFLICT (code) DO NOTHING;

-- Map existing cameras to corresponding groups and hierarchies based on name and stream_id
UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110010',
    zone = 'Ahmedabad Zone',
    district = 'Ahmedabad',
    subdivision = 'SG Highway Division',
    police_station = 'Vastrapur / SG Highway Traffic PS'
WHERE stream_id IN (1, 5, 16) OR lower(name) LIKE '%visat%' OR lower(name) LIKE '%chiman%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110011',
    zone = 'Ahmedabad Zone',
    district = 'Ahmedabad',
    subdivision = 'Central Division',
    police_station = 'Kalupur Police Station'
WHERE stream_id = 4 OR lower(name) LIKE '%paldi%' OR lower(name) LIKE '%kalupur%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110012',
    zone = 'Ahmedabad Zone',
    district = 'Ahmedabad',
    subdivision = 'East Division',
    police_station = 'Naroda Police Station'
WHERE lower(name) LIKE '%naroda%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110013',
    zone = 'Ahmedabad Zone',
    district = 'Ahmedabad',
    subdivision = 'East Division',
    police_station = 'Bapunagar Police Station'
WHERE lower(name) LIKE '%bapunagar%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110014',
    zone = 'Ahmedabad Zone',
    district = 'Ahmedabad',
    subdivision = 'Ring Road Division',
    police_station = 'SP Ring Road Traffic Unit'
WHERE stream_id IN (3, 7, 14, 28) OR lower(name) LIKE '%ring road%' OR lower(name) LIKE '%mervada%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110015',
    zone = 'Ahmedabad Zone',
    district = 'Ahmedabad',
    subdivision = 'South Division',
    police_station = 'Maninagar Police Station'
WHERE lower(name) LIKE '%maninagar%' OR lower(name) LIKE '%suvidha%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110016',
    zone = 'Ahmedabad Zone',
    district = 'Ahmedabad',
    subdivision = 'West Division',
    police_station = 'Ellisbridge Police Station'
WHERE lower(name) LIKE '%ellisbridge%' OR lower(name) LIKE '%vidhyalaya%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110005',
    zone = 'Rajkot Range',
    district = 'Rajkot',
    subdivision = 'Rajkot City',
    police_station = 'Rajkot Bus Port PS'
WHERE stream_id IN (17, 18) OR lower(name) LIKE '%rajkot%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110003',
    zone = 'Gandhinagar Range',
    district = 'Gandhinagar',
    subdivision = 'Adalaj Sub-Division',
    police_station = 'Adalaj Police Station'
WHERE stream_id IN (12, 33) OR lower(name) LIKE '%adalaj%' OR lower(name) LIKE '%dehgam%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110004',
    zone = 'Surat City Police Zone',
    district = 'Navsari / Surat',
    subdivision = 'Bilimora Division',
    police_station = 'Bilimora Police Station'
WHERE stream_id IN (34, 35, 36, 37) OR lower(name) LIKE '%bilimora%' OR lower(name) LIKE '%dhanori%' OR lower(name) LIKE '%tankal%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110007',
    zone = 'Coastal & Border Security Range',
    district = 'Junagadh',
    subdivision = 'Junagadh Division',
    police_station = 'Timbavadi Gate PS'
WHERE stream_id IN (6, 9) OR lower(name) LIKE '%junagadh%';

UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110008',
    zone = 'State Highway Patrol Corridor',
    district = 'Patan',
    subdivision = 'Highway Patrol',
    police_station = 'Patan Dethali Highway PS'
WHERE stream_id = 23 OR lower(name) LIKE '%patan%';

-- Fallback for any unassigned
UPDATE cameras SET
    group_id = '11111111-1111-1111-1111-111111110002'
WHERE group_id IS NULL;
