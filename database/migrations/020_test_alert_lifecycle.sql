-- Test alerts mirror the operational lifecycle without touching production alerts.
ALTER TABLE test_alerts
  ADD COLUMN IF NOT EXISTS status VARCHAR(24) NOT NULL DEFAULT 'NEW',
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS acknowledged_by VARCHAR(128),
  ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(128),
  ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS closed_by VARCHAR(128);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='test_alert_status_check') THEN
    ALTER TABLE test_alerts ADD CONSTRAINT test_alert_status_check
      CHECK (status IN ('NEW','ACKNOWLEDGED','INVESTIGATING','RESOLVED','CLOSED'));
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_test_alerts_status ON test_alerts(session_id, status, created_at DESC);
