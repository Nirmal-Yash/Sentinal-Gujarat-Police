#!/usr/bin/env python3
"""Consolidated repository release gate; fails on any required contract gap."""
from pathlib import Path
import re, sys
ROOT = Path(__file__).resolve().parents[1]
required = [
    'ai_engine/anpr_policy.py','ai_engine/anpr_worker.py','ai_engine/yolo_worker.py',
    'ai_engine/event_schema.py','intelligence/sighting_store.py','intelligence/alert_engine.py','intelligence/evidence_capture.py',
    'api/auth.py','api/migrations.py','api/routes/cameras.py','api/routes/search.py','api/routes/reports.py','api/routes/alerts.py','api/routes/evidence.py','api/routes/operations.py','api/routes/test.py','api/routes/test_alerts.py',
    'dashboard/src/components/MapView.jsx','dashboard/src/components/AlertPanel.jsx',
    'database/migrations/011_vehicle_journey_domain.sql','database/migrations/012_runtime_integrity_and_dedup.sql','database/migrations/020_test_alert_lifecycle.sql',
]
missing = [p for p in required if not (ROOT / p).exists()]
for p in required:
    print('[%s] %s' % ('OK' if p not in missing else 'FAIL', p))
files = sorted((ROOT / 'database/migrations').glob('*.sql'))
parsed = [re.match(r'^(\d+)_', p.name) for p in files]
if any(m is None for m in parsed):
    missing.append('invalid migration filename')
versions = [m.group(1) for m in parsed if m]
if len(versions) != len(set(versions)):
    missing.append('duplicate migration versions')
if '012_sighting_deduplication.sql' in [p.name for p in files]:
    missing.append('duplicate 012 migration remains')
print('[%s] unique migration numbering' % ('OK' if len(versions) == len(set(versions)) else 'FAIL'))
if missing:
    print('\nFINAL_CI_GATE=FAIL')
    sys.exit(1)
print('\nFINAL_CI_GATE=PASS')
