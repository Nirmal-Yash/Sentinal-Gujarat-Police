-- Repair existing databases where 008 was recorded before this additive field
-- was introduced. Safe and isolated to the test-session namespace.
ALTER TABLE test_session_feeds ADD COLUMN IF NOT EXISTS loop BOOLEAN NOT NULL DEFAULT TRUE;
