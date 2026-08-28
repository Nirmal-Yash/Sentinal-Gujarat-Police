-- Operational RBAC roles: preserve existing users while allowing investigator/auditor separation.
DO $$
BEGIN
  ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
  ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('SUPERADMIN','ADMIN','OPERATOR','INVESTIGATOR','VIEWER','AUDITOR'));
END $$;

CREATE INDEX IF NOT EXISTS idx_users_role_active ON users(role, is_active);
