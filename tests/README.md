Sentinel System Test Suite

Seed RBAC users:
RBAC_TEST_PASSWORD='Test@12345' python scripts/seed_rbac_test_users.py

API suite:
SENTINEL_BASE_URL=http://localhost:8000 RBAC_TEST_PASSWORD='Test@12345' pytest tests/api

Integration suite:
SENTINEL_BASE_URL=http://localhost:8000 RBAC_TEST_PASSWORD='Test@12345' pytest tests/integration

End-to-end suite:
SENTINEL_BASE_URL=http://localhost:8000 RBAC_TEST_PASSWORD='Test@12345' pytest tests/e2e

The suite checks success, validation, authentication, authorization, not-found, conflict, payload-size, content-type, rate/operational boundary behavior, all six RBAC roles, CCTV scoping, evidence traversal, test-mode isolation, Redis/PostgreSQL runtime visibility, and full user-to-dashboard paths.
