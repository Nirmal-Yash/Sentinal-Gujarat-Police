-- Operational alert lifecycle and auditable evidence references.
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'NEW';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(255);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS closed_by VARCHAR(255);
CREATE INDEX IF NOT EXISTS idx_alerts_status_created ON alerts(status, created_at DESC);

CREATE TABLE IF NOT EXISTS evidence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(255),
    alert_id UUID REFERENCES alerts(id) ON DELETE SET NULL,
    camera_id UUID REFERENCES cameras(id) ON DELETE SET NULL,
    captured_at TIMESTAMPTZ,
    media_type VARCHAR(64) NOT NULL,
    storage_key TEXT NOT NULL,
    sha256 VARCHAR(128),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_evidence_alert ON evidence(alert_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_event ON evidence(event_id, created_at DESC);

CREATE TABLE IF NOT EXISTS alert_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    actor VARCHAR(255) NOT NULL,
    action VARCHAR(64) NOT NULL,
    from_status VARCHAR(32),
    to_status VARCHAR(32),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alert_audit_alert ON alert_audit_log(alert_id, created_at DESC);
