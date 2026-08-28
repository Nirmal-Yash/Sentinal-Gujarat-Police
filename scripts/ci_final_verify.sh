#!/usr/bin/env bash
set -euo pipefail
python scripts/final_integration_gate.py
python scripts/validate_refactor.py
python scripts/anpr_benchmark.py scripts/fixtures/anpr_benchmark_smoke.csv --max-error-rate 0.50
python scripts/registry_load_smoke.py
python -m py_compile ai_engine/*.py ingestion/*.py intelligence/*.py api/*.py api/routes/*.py
