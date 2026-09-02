-- Security hardening state; independent from operational business tables.
CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti UUID PRIMARY KEY,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_tokens(expires_at);

CREATE TABLE IF NOT EXISTS auth_attempts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(128),
    ip_hash VARCHAR(64) NOT NULL,
    succeeded BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_user_time ON auth_attempts(username, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_ip_time ON auth_attempts(ip_hash, created_at DESC);

CREATE TABLE IF NOT EXISTS security_audit_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(80) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    actor VARCHAR(255) NOT NULL DEFAULT 'system',
    message TEXT NOT NULL,
    ip_address VARCHAR(128),
    user_agent VARCHAR(255),
    request_id VARCHAR(128),
    payload_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_security_audit_type_time ON security_audit_events(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_audit_actor_time ON security_audit_events(actor, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_audit_severity_time ON security_audit_events(severity, created_at DESC);

ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS encrypted_description TEXT;
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS encrypted_notes TEXT;
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS encrypted_embedding BYTEA;

CREATE INDEX IF NOT EXISTS idx_auth_attempts_cleanup ON auth_attempts(created_at);
CREATE INDEX IF NOT EXISTS idx_security_audit_cleanup ON security_audit_events(created_at);
