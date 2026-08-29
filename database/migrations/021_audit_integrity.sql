-- Append-only, hash-chained audit integrity for operational/legal traceability.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE camera_audit_log ADD COLUMN IF NOT EXISTS audit_seq BIGINT;
ALTER TABLE camera_audit_log ADD COLUMN IF NOT EXISTS prev_hash TEXT;
ALTER TABLE camera_audit_log ADD COLUMN IF NOT EXISTS entry_hash TEXT;
ALTER TABLE camera_audit_log ADD COLUMN IF NOT EXISTS immutable_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE SEQUENCE IF NOT EXISTS camera_audit_log_seq;
UPDATE camera_audit_log SET audit_seq=nextval('camera_audit_log_seq') WHERE audit_seq IS NULL;
ALTER TABLE camera_audit_log ALTER COLUMN audit_seq SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_camera_audit_seq ON camera_audit_log(audit_seq);

CREATE OR REPLACE FUNCTION camera_audit_hash_row() RETURNS trigger AS $$
DECLARE
    previous_hash TEXT;
    canonical TEXT;
BEGIN
    PERFORM pg_advisory_xact_lock(2147483121);
    IF TG_OP = 'INSERT' THEN
        IF NEW.audit_seq IS NULL THEN NEW.audit_seq := nextval('camera_audit_log_seq'); END IF;
        SELECT entry_hash INTO previous_hash FROM camera_audit_log ORDER BY audit_seq DESC LIMIT 1;
        NEW.prev_hash := previous_hash;
        canonical := concat_ws('|', NEW.audit_seq, NEW.camera_id, NEW.actor, NEW.action,
            COALESCE(NEW.before_value::text,''), COALESCE(NEW.after_value::text,''),
            COALESCE(NEW.correlation_id::text,''), NEW.created_at, NEW.immutable_at, COALESCE(previous_hash,''));
        NEW.entry_hash := encode(digest(canonical, 'sha256'), 'hex');
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'camera_audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS camera_audit_hash_insert ON camera_audit_log;
CREATE TRIGGER camera_audit_hash_insert
    BEFORE INSERT OR UPDATE OR DELETE ON camera_audit_log
    FOR EACH ROW EXECUTE FUNCTION camera_audit_hash_row();

CREATE OR REPLACE FUNCTION prevent_camera_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'camera_audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS camera_audit_no_update ON camera_audit_log;
DROP TRIGGER IF EXISTS camera_audit_no_delete ON camera_audit_log;
CREATE TRIGGER camera_audit_no_update BEFORE UPDATE ON camera_audit_log FOR EACH ROW EXECUTE FUNCTION prevent_camera_audit_mutation();
CREATE TRIGGER camera_audit_no_delete BEFORE DELETE ON camera_audit_log FOR EACH ROW EXECUTE FUNCTION prevent_camera_audit_mutation();

CREATE OR REPLACE FUNCTION verify_camera_audit_chain() RETURNS TABLE(audit_seq BIGINT, valid BOOLEAN) AS $$
DECLARE
    row_data RECORD;
    expected TEXT;
    prior TEXT := NULL;
BEGIN
    FOR row_data IN SELECT * FROM camera_audit_log ORDER BY audit_seq LOOP
        expected := encode(digest(concat_ws('|', row_data.audit_seq, row_data.camera_id, row_data.actor, row_data.action,
            COALESCE(row_data.before_value::text,''), COALESCE(row_data.after_value::text,''),
            COALESCE(row_data.correlation_id::text,''), row_data.created_at, row_data.immutable_at, COALESCE(row_data.prev_hash,'')), 'sha256'), 'hex');
        audit_seq := row_data.audit_seq;
        valid := row_data.prev_hash IS NOT DISTINCT FROM prior AND row_data.entry_hash = expected;
        RETURN NEXT;
        prior := row_data.entry_hash;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

CREATE INDEX IF NOT EXISTS idx_camera_audit_actor_time ON camera_audit_log(actor, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_camera_audit_camera_time ON camera_audit_log(camera_id, created_at DESC);
