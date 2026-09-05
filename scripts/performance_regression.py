#!/usr/bin/env python3
"""Static regression gate for Sentinel ingestion/AI performance contracts."""
from pathlib import Path
import ast, sys

ROOT=Path(__file__).resolve().parents[1]
fail=[]

def check(condition,message):
    print(("[OK]   " if condition else "[FAIL] ")+message)
    if not condition: fail.append(message)

def read(path):
    p=ROOT/path
    return p.read_text(encoding="utf-8") if p.is_file() else ""

ing=read(Path("ingestion/worker.py"))
ai=read(Path("ai_engine/anpr_worker.py"))
policy=read(Path("ai_engine/anpr_policy.py"))
main=read(Path("ai_engine/main.py"))
grid=read(Path("dashboard/src/components/CameraGrid.jsx"))
manager=read(Path("dashboard/src/components/cameraPlayerManager.js"))
gateway=read(Path("api/services/cctv_gateway.py"))
catalogue=read(Path("ingestion/catalogue_sync.py"))
compose=read(Path("docker-compose.yml"))

check("FRAME_GATE_ENABLED" in ing and "np.mean(cv2.absdiff" in ing,"motion gating is implemented")
check("ALIVE_KEY" in ing and "ALIVE_INTERVAL" in ing,"camera-alive telemetry is independent")
check("RAW_STREAM_MAX" in ing and "processing_interval_ms" in ing,"raw stream is bounded and carries sampling metadata")
check("CATEGORY_INTERVALS" in ing and all(v in ing for v in ("0.300","0.500","0.800")),"sampling categories remain defined")
check("ProcessPoolExecutor" in ai and "MAX_PENDING_JOBS" in ai,"ANPR OCR work is bounded")
check("window_seconds" in policy and "min_track_age" in policy,"ANPR policy is time-windowed")
check("_preload_models" in main and "set_yolo_model" in main,"AI shared-model preload is present")
check("IntersectionObserver" in manager and "MAX_PLAYERS=12" in manager,"frontend player budget is centralized")
check("/api/cctv/" in grid and "testMode" in grid,"dashboard feed routing distinguishes production/test")
check("CCTV_EMAIL" in gateway and "CCTV_EMAIL" in catalogue and "CCTV_EMAIL" in compose,"CCTV email credential is wired end-to-end")

for rel in ["ingestion/worker.py","ai_engine/anpr_worker.py","ai_engine/anpr_policy.py","api/services/cctv_gateway.py","ingestion/catalogue_sync.py","scripts/performance_regression.py"]:
    try:
        ast.parse(read(Path(rel)),filename=rel)
        check(True,f"{rel} parses")
    except SyntaxError as exc:
        check(False,f"{rel} syntax: {exc}")

if fail:
    print(f"\n{len(fail)} gate(s) failed.")
    sys.exit(1)
print("\nAll performance regression gates passed.")
