#!/usr/bin/env python3
"""Local regression gate for the coordinated performance optimisation."""
from __future__ import annotations
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FAIL=[]

def check(ok,message):
    print(("[OK]   " if ok else "[FAIL] ")+message)
    if not ok: FAIL.append(message)

compose=(ROOT/"docker-compose.yml").read_text()
ing=(ROOT/"ingestion/worker.py").read_text()
yolo=(ROOT/"ai_engine/yolo_worker.py").read_text()
anpr=(ROOT/"ai_engine/anpr_worker.py").read_text()
policy=(ROOT/"ai_engine/anpr_policy.py").read_text()
main=(ROOT/"ai_engine/main.py").read_text()
grid=(ROOT/"dashboard/src/components/CameraGrid.jsx").read_text()
manager=(ROOT/"dashboard/src/components/cameraPlayerManager.js").read_text()
app=(ROOT/"dashboard/src/App.jsx").read_text()
face=(ROOT/"ai_engine/face_worker.py").read_text()

check("FRAME_GATE_ENABLED" in compose and "RAW_FRAME_STREAM_MAXLEN" in compose,"frame-gate settings are configured")
check("CATEGORY_INTERVALS" in ing and "0.300" in ing and "0.500" in ing and "0.800" in ing,"camera sampling categories are implemented")
check("np.mean(cv2.absdiff" in ing and "THUMBNAIL_SIZE" in ing,"motion measurement uses a small thumbnail")
check("camera_alive" in ing and "self.r.hset(ALIVE_KEY" in ing,"camera-alive signal is independent of AI frame forwarding")
check("maxlen=RAW_STREAM_MAX" in ing and "processing_interval_ms" in ing,"raw frame stream is bounded and carries sampling metadata")
check("window_seconds" in policy and "observed_at >= current - self.window_seconds" in policy,"ANPR voting window is wall-clock based")
check("first_seen_at" in policy and "min_track_age" in policy,"ANPR track-age gate is time based")
check("ProcessPoolExecutor" in anpr and "MAX_PENDING_JOBS" in anpr and 'get_context("fork")' in anpr,"ANPR OCR uses bounded forked worker pool")
check("_preprocess_for_ocr" in anpr and "createCLAHE" in anpr and "addWeighted" in anpr,"ANPR preprocessing uses grayscale CLAHE and sharpening")
check("_preload_models" in main and "get_start_method" in main and "_preload_models(ANPR_ENABLED, FACE_ENABLED)" in main,"AI models are preloaded before worker creation")
check("get_yolo_model()" in yolo and "get_yolo_model()" in face,"preloaded YOLO model is reused by YOLO and face workers")
check("IntersectionObserver" in manager and "rootMargin:'200px 0px'" in manager and "MAX_PLAYERS=12" in manager,"frontend uses one observer and a 12-player budget")
check("OFFSCREEN_DELAY" in manager and "visibilitychange" in manager,"frontend suspends offscreen and hidden-tab players")
check("function LivePlayer" in grid and "'SUSPENDED'" in grid and "'ERROR'" in grid and "15000" in grid,"player lifecycle and 15s snapshot refresh are present")
check("wsBatchRef" in app and "500" in app,"WebSocket non-critical updates are batched")
check((ROOT/"database/migrations/025_performance_processing_category.sql").exists(),"performance registry migration exists")
check((ROOT/"ai_engine/thresholds.yaml").exists(),"ANPR thresholds YAML exists")
check(not (ROOT/".github/workflows").exists() or not list((ROOT/".github/workflows").glob("*")),"no GitHub Actions workflow is introduced")
try:
    sys.path.insert(0,str(ROOT/"ai_engine"))
    from anpr_policy import TrackANPRState, PlateObservation
    state=TrackANPRState(window_seconds=8.0)
    for t in (0.0,1.5,3.0,7.5):
        state.add(PlateObservation("GJ01AB1234",.95,.95,.95,True,t))
    check(state.consensus(4,7.5)[0]=="GJ01AB1234","time-window consensus confirms repeated agreement")
    state.add(PlateObservation("GJ01AB1234",.95,.95,.95,True,10.0))
    check(state.consensus(4,10.0)[0] is None,"old ANPR votes expire outside eight-second window")
    check(TrackANPRState(window_seconds=8.0).window_seconds==8.0,"ANPR time window initializes cleanly")
except Exception as exc:
    check(False,f"ANPR policy regression executes: {exc}")

if FAIL:
    print("\n"+str(len(FAIL))+" performance gate(s) failed.")
    raise SystemExit(1)
print("\nAll performance gates passed.")
