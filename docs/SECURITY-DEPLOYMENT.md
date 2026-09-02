# Sentinel AI — Production Security Deployment

## Required production secrets

Set these outside source control:

- `SECRET_KEY`: long random access-token signing secret.
- `JWT_REFRESH_SECRET_KEY`: different long random refresh-token signing secret.
- `SNAPSHOT_TOKEN_SECRET`: long random signed-media secret.
- `FIELD_ENCRYPTION_KEY`: Fernet key for encrypted evidence/sensitive fields.
- `POSTGRES_PASSWORD`: strong database credential.
- `REDIS_PASSWORD`: strong Redis credential when Redis authentication is enabled.
- `CCTV_PASSWORD`: assigned CCTV provider password.

Never commit `.env`, secret files, private keys, or live credentials.

## Data in transit

Production browser traffic must terminate TLS before the dashboard/API is exposed. Set `AUTH_COOKIE_SECURE=true` and `FORCE_SECURITY_HEADERS=true` behind HTTPS so session cookies are Secure and HSTS is emitted.

Set `DB_SSL=1` when PostgreSQL is reached over a TLS-capable connection. The application connection pool uses pre-ping, bounded overflow, connection recycling, statement timeout, and lock timeout.

For Redis deployments that provide TLS, use a `rediss://` Redis URL and enable Redis authentication. Local Docker development may keep the existing internal non-TLS Redis URL.

The CCTV provider remains HTTPS (`cctv.corp8.cloud`); the browser never receives `CCTV_PASSWORD`.

## Data at rest

Evidence capture computes SHA-256 over the original evidence bytes. When `FIELD_ENCRYPTION_KEY` is configured, evidence is stored encrypted on disk with a `.enc` suffix and decrypted only by the authenticated signed-evidence endpoint.

PostgreSQL, Redis, and Docker volumes should additionally be protected by encrypted host/storage volumes in the production environment. Application-level encryption is not a substitute for encrypted infrastructure storage.

Face embeddings remain queryable in PostgreSQL/pgvector because replacing the vector with ciphertext would disable the existing similarity-search feature. Protect the database volume and access controls instead.

## Authentication

Access tokens are short-lived (15 minutes by default). Refresh tokens are stored in an HttpOnly cookie, rotated on every refresh, and revoked by JTI. The application also limits concurrent sessions and applies user/IP login-failure lockout.

## Acceptance checks

1. `docker compose config -q`
2. `GET /health` returns `200`
3. `GET /ready` returns `200` with all checks true
4. Browser login sets `sentinel_session` and `sentinel_refresh` HttpOnly cookies
5. Expiring access token transparently refreshes once and retries the original request
6. `security_audit_events` receives successful/failed security-relevant request events
7. Evidence on disk is ciphertext when `FIELD_ENCRYPTION_KEY` is enabled
8. Signed evidence returns the original bytes and the stored SHA-256 header
9. Production rejects missing field-encryption/DB-TLS/secure-cookie configuration
10. Existing three CI release checks remain the only release checks
