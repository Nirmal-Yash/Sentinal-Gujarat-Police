-- Coordinate registry supplied for the current camera catalogue.  These
-- values replace only the legacy empty coordinate state and retain provenance.
UPDATE cameras AS c
SET location = v.location || ', ' || v.city,
    lat = v.lat,
    lng = v.lng,
    coord_source = v.source,
    coord_confidence = v.confidence,
    department = v.department,
    geom = ST_SetSRID(ST_MakePoint(v.lng, v.lat), 4326),
    updated_at = NOW()
FROM (VALUES
  (1, 'Chiman bhai Bridge', 'Ahmedabad', 23.0260::double precision, 72.5780::double precision, 'geocoded', .55::double precision, 'AMC / Gujarat Police'),
  (2, 'Janpath', 'Ahmedabad', 23.0380, 72.5620, 'geocoded', .60, 'AMC'),
  (3, 'O.N.G.C. Office', 'Ahmedabad', 23.0267, 72.5879, 'geocoded', .65, 'ONGC / Gujarat Police'),
  (4, 'Paldi Circle', 'Ahmedabad', 23.0127, 72.5810, 'geocoded', .70, 'AMC'),
  (5, 'Visat teen Rasta', 'Ahmedabad', 23.0907, 72.5960, 'geocoded', .70, 'Gujarat Police'),
  (6, 'Timbavadi gate-Junagadh', 'Junagadh', 21.5192, 70.4515, 'geocoded', .70, 'Gujarat Police Junagadh'),
  (7, 'hero-showroom-gir-somnath', 'Gir Somnath', 20.9073, 70.3638, 'geocoded', .50, 'Gir Somnath Police'),
  (8, 'majewadi-gate-junagadh', 'Junagadh', 21.5225, 70.4647, 'geocoded', .75, 'Gujarat Police Junagadh'),
  (9, 'new-bypass-near-by-circle-junagadh-2', 'Junagadh', 21.5080, 70.4780, 'geocoded', .65, 'Gujarat Police Junagadh'),
  (10, 'char-chowk-road-2-junagadh', 'Junagadh', 21.5225, 70.4590, 'geocoded', .70, 'Gujarat Police Junagadh'),
  (11, 'dolatpara-junagadh', 'Junagadh', 21.5310, 70.4820, 'geocoded', .70, 'Gujarat Police Junagadh'),
  (12, 'Tri Mandir Adalaj Tollnaka', 'Gandhinagar', 23.1644, 72.5758, 'geocoded', .80, 'NHAI / Gujarat Police'),
  (13, 'CN Vidhyalaya', 'Ahmedabad', 23.0327, 72.5493, 'geocoded', .70, 'AMC'),
  (14, 'Delight', 'Ahmedabad', 23.0365, 72.5502, 'geocoded', .40, 'AMC'),
  (15, 'Suvidha park', 'Ahmedabad', 23.0477, 72.5893, 'geocoded', .50, 'AMC'),
  (16, 'Visat P2', 'Ahmedabad', 23.0958, 72.5997, 'geocoded', .70, 'Gujarat Police'),
  (17, 'Rajkot Bus Port CCTV', 'Rajkot', 22.2956, 70.7804, 'geocoded', .85, 'GSRTC / Rajkot Police'),
  (18, 'Rajkot CCTV', 'Rajkot', 22.3117, 70.8022, 'geocoded', .50, 'Rajkot Police'),
  (19, 'KHAPARIA, GANDEVI, NAVSARI', 'Navsari', 20.7972, 73.0130, 'geocoded', .85, 'Gram Panchayat Navsari'),
  (20, 'Mohanpura', 'Rajkot', 22.3175, 70.8352, 'geocoded', .55, 'Rajkot Municipal'),
  (21, 'Patan Dethali Char Rasta', 'Patan', 23.8500, 72.1300, 'geocoded', .65, 'Gujarat Police Patan'),
  (22, 'BK Mervada tran Rasta', 'Bhavnagar region', 21.7700, 72.1500, 'default', .35, 'Gujarat Police'),
  (23, 'kheram', 'Navsari/Valsad', 20.6500, 72.9300, 'default', .35, 'Gram Panchayat'),
  (24, 'dehgam', 'Gandhinagar', 23.1753, 73.0133, 'geocoded', .80, 'Gujarat Police Gandhinagar'),
  (25, 'dhanori', 'Vadodara/Navsari', 21.1700, 73.0200, 'default', .30, 'Unknown'),
  (26, 'TANKAL', 'North Gujarat', 23.5500, 72.5000, 'default', .30, 'Unknown'),
  (27, 'bilimora', 'Navsari', 20.7678, 72.9786, 'geocoded', .85, 'Navsari Police'),
  (28, 'bilimora', 'Navsari', 20.7650, 72.9810, 'geocoded', .85, 'Navsari Police'),
  (29, 'bilimora', 'Navsari', 20.7700, 72.9762, 'geocoded', .85, 'Navsari Police'),
  (30, 'Gandhidham Rambaugh p2', 'Kutch', 23.0753, 70.1337, 'geocoded', .80, 'Gandhidham Police / Kutch')
) AS v(stream_id, location, city, lat, lng, source, confidence, department)
WHERE c.stream_id = v.stream_id;
