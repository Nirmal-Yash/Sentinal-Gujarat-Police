-- Optional procurement/maintenance registry. Camera facts remain canonical in
-- cameras; vendor/model records only provide normalized reference data.
CREATE TABLE IF NOT EXISTS vendors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    contact_name VARCHAR(255), contact_email VARCHAR(255), contact_phone VARCHAR(64),
    support_url VARCHAR(512),
    protocol_support TEXT[] NOT NULL DEFAULT ARRAY['RTSP']::TEXT[],
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT vendors_protocol_support CHECK (protocol_support <@ ARRAY['RTSP','ONVIF']::TEXT[])
);
CREATE TABLE IF NOT EXISTS camera_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL, camera_type VARCHAR(100) NOT NULL DEFAULT 'fixed',
    default_codec VARCHAR(64), default_width INTEGER, default_height INTEGER, default_fps DOUBLE PRECISION,
    analytics_capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(vendor_id, name)
);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS vendor_id UUID REFERENCES vendors(id) ON DELETE SET NULL;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS model_id UUID REFERENCES camera_models(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_cameras_vendor_id ON cameras(vendor_id);
CREATE INDEX IF NOT EXISTS idx_cameras_model_id ON cameras(model_id);
