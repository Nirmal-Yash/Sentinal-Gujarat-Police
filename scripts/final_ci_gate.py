#!/usr/bin/env python3
"""Deterministic repository and service-contract gate for Sentinel."""
from __future__ import annotations

from pathlib import Path
import re, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
failures = []

def read(rel):
    path = ROOT / rel
    if not path.is_file():
        failures.append(f'missing required file: {rel}')
        return ''
    return path.read_text(encoding='utf-8')

def check(ok, message):
    print(f"[{'OK' if ok else 'FAIL'}] {message}")
    if not ok:
        failures.append(message)

def main():
    required = [
        '.env.example', 'docker-compose.yml', 'api/main.py',
        'api/routes/test.py', 'api/routes/test_alerts.py', 'api/routes/search.py', 'api/routes/watchlist.py', 'api/routes/camera_imports.py',
        'ai_engine/main.py', 'ai_engine/face_worker.py', 'ai_engine/person_investigation_worker.py', 'ai_engine/anpr_worker.py', 'ai_engine/thresholds.yaml',
        'ingestion/worker.py', 'ingestion/test_runner.py', 'ingestion/stream_adapters.py', 'intelligence/test_sighting_store.py',
        'dashboard/src/App.jsx', 'dashboard/src/api/client.js', 'dashboard/src/components/TestFeedManager.jsx', 'dashboard/src/components/WatchlistModal.jsx', 'dashboard/src/components/CameraGrid.jsx',
        'database/migrations/019_rbac_roles.sql', 'database/migrations/020_test_alert_lifecycle.sql', 'database/migrations/021_audit_integrity.sql', 'database/migrations/023_p1_intelligence_consistency.sql', 'database/migrations/024_stream_metadata_provenance.sql', 'database/migrations/025_processing_fps_category.sql', 'database/migrations/026_test_watchlists.sql',
    ]
    for rel in required:
        check((ROOT / rel).is_file(), f'required component exists: {rel}')

    auth = read('api/auth.py')
    for role in ('VIEWER','OPERATOR','INVESTIGATOR','AUDITOR','ADMIN','SUPERADMIN'): check(role in auth, f'RBAC role exists: {role}')
    for perm in ('camera:read','camera:write','alert:read','alert:operate','search:read','evidence:read','evidence:create','registry:admin','audit:read','system:admin'): check(perm in auth, f'RBAC capability exists: {perm}')

    app = read('dashboard/src/App.jsx'); client = read('dashboard/src/api/client.js')
    check('storedTestSessionId' in app and 'api.getActiveTestSession()' in app and 'setTestMode(true)' in app, 'Test mode restores persisted session')
    check('Object.entries(p).filter' in client, 'query builders remove undefined filters')
    check('getTestWatchlist' in client and 'addTestWatchlistPersonPhoto' in client, 'Test Watchlist API is wired')

    test_api = read('api/routes/test.py'); test_alerts = read('api/routes/test_alerts.py'); search = read('api/routes/search.py'); sight = read('intelligence/test_sighting_store.py')
    check('@router.post("/sessions/{session_id}/feeds"' in test_api and '@router.delete("/sessions/{session_id}/feeds/{stream_id}")' in test_api, 'Test Feed lifecycle exists')
    check('@router.post("/sessions/{session_id}/watchlist/person-photo")' in test_api and 'test_watchlists' in test_api, 'Test Watchlist lifecycle exists')
    check('test_watchlists' in search and 'X-Test-Session-Id' in search, 'Test search routing is isolated')
    check('FROM test_watchlists' in sight and 'FROM watchlist' not in sight, 'Test Intelligence never reads Production watchlists')
    check('priority.lower() in {"undefined", "null"}' in test_alerts, 'Test Alert filters sanitize undefined values')

    face = read('ai_engine/face_worker.py'); person = read('ai_engine/person_investigation_worker.py'); yolo = read('ai_engine/yolo_worker.py'); anpr = read('ai_engine/anpr_worker.py')
    check('IN_STREAM = f"{PREFIX}raw_frames"' in face and 'OUT_STREAM = f"{PREFIX}detections"' in face, 'Face worker stream contract exists')
    check('fx1,fy1' in face and 'HEALTH_PREFIX' in face, 'Face worker emits face boxes and heartbeat')
    check('HEALTH_PREFIX' in person and 'embeddings' in person and 'face_count' in person, 'Person worker exposes readiness and embeddings')
    check('IN_STREAM = f"{PREFIX}raw_frames"' in yolo and 'OUT_STREAM = f"{PREFIX}detections"' in yolo, 'YOLO worker stream contract exists')
    check('MAX_PENDING_JOBS' in anpr and 'VOTE_WINDOW_SECS' in anpr, 'ANPR controls are bounded')

    ingestion = read('ingestion/worker.py'); adapter = read('ingestion/stream_adapters.py'); runner = read('ingestion/test_runner.py')
    check('STREAM_KEY = "raw_frames"' in ingestion and 'FRAME_GATE_ENABLED' in ingestion, 'Production ingestion publishes raw frames')
    check('CCTV_EMAIL' in adapter and 'quote(email, safe=' in adapter, 'RTSP adapter injects encoded credentials')
    check('test:raw_frames' in runner, 'Test runner publishes isolated frames')

    compose = read('docker-compose.yml')
    check('test_ai_worker:' in compose and 'test_person_investigation:' in compose and 'test_intelligence:' in compose, 'Docker has isolated Test services')
    check('FACE_ENABLED=${TEST_FACE_ENABLED:-true}' in compose, 'Test Face is enabled by default')
    check('AI_HEALTH_PREFIX' in compose and 'AI_HEALTH_TTL_SECS' in compose, 'AI health config is exposed to Docker')

    for root in ('api','ingestion','intelligence','ai_engine'):
        for path in (ROOT / root).rglob('*.py'):
            if '__pycache__' in path.parts: continue
            result = subprocess.run([sys.executable,'-m','py_compile',str(path)],cwd=ROOT,text=True,capture_output=True)
            check(result.returncode == 0, f'Python syntax compiles: {path.relative_to(ROOT)}')

    if failures:
        print(f'\nFINAL_CI_GATE=FAIL ({len(failures)} failures)')
        return 1
    print('\nFINAL_CI_GATE=PASS')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())