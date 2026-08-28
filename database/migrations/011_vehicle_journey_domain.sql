-- Explicit vehicle identity and journey domain. Detections remain high-volume analytics data;
-- sightings/journeys remain durable investigation/business records.
CREATE TABLE IF NOT EXISTS vehicle_identities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_key VARCHAR(255) NOT NULL UNIQUE,
    identity_type VARCHAR(32) NOT NULL DEFAULT 'PLATE_CONFIRMED',
    normalized_plate VARCHAR(100),
    confidence DOUBLE PRECISION,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vehicle_identity_plate ON vehicle_identities(normalized_plate);

CREATE TABLE IF NOT EXISTS vehicle_journeys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vehicle_identity_id UUID NOT NULL REFERENCES vehicle_identities(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NOT NULL,
    sighting_count INTEGER NOT NULL DEFAULT 0,
    journey_confidence DOUBLE PRECISION,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vehicle_journeys_identity_time ON vehicle_journeys(vehicle_identity_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_vehicle_journeys_recent ON vehicle_journeys(ended_at DESC);

CREATE TABLE IF NOT EXISTS vehicle_journey_sightings (
    journey_id UUID NOT NULL REFERENCES vehicle_journeys(id) ON DELETE CASCADE,
    sighting_id UUID NOT NULL REFERENCES vehicle_sightings(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (journey_id, sighting_id),
    UNIQUE (journey_id, sequence_no)
);
CREATE INDEX IF NOT EXISTS idx_journey_sightings_order ON vehicle_journey_sightings(journey_id, sequence_no);

ALTER TABLE vehicle_sightings ADD COLUMN IF NOT EXISTS identity_type VARCHAR(32) NOT NULL DEFAULT 'PLATE_CONFIRMED';
ALTER TABLE vehicle_sightings ADD COLUMN IF NOT EXISTS journey_id UUID REFERENCES vehicle_journeys(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_sightings_identity_time ON vehicle_sightings(global_vehicle_id, source_timestamp DESC);
