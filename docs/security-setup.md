# RBAC and synthetic diagnostics setup

Local compatibility mode remains the default so the existing evaluation stack
does not lose access.  Before any shared or production deployment, set a unique
`SECRET_KEY`, `AUTH_REQUIRED=true`, and seed the first account from environment
values only:

```powershell
$env:SENTINEL_ADMIN_USERNAME = 'approved-admin-name'
$env:SENTINEL_ADMIN_PASSWORD = 'use-a-secret-manager-generated-password'
$env:SENTINEL_ADMIN_ROLE = 'SUPERADMIN'
docker compose exec -e SENTINEL_ADMIN_USERNAME -e SENTINEL_ADMIN_PASSWORD -e SENTINEL_ADMIN_ROLE api python seed_admin.py
```

No username or password is embedded in code, migrations, Docker images, or the
database initializer.  Enable `TEST_ENDPOINT_ENABLED=true` only alongside RBAC;
test events use `test_*` tables and `test:{session}:*` Redis keys exclusively.
