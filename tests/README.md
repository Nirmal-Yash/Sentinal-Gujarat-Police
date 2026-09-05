# Sentinel test suite

Static contract tests run without live CCTV credentials or external services.

- python scripts/final_ci_gate.py
- python scripts/final_integration_gate.py
- python scripts/validate_refactor.py
- python scripts/performance_regression.py
- pytest -q tests/test_*_contract.py

Runtime integration scripts require configured PostgreSQL, Redis and related services and are intentionally separate from the static release gate.
