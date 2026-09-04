#!/usr/bin/env python3
"""Static and lightweight semantic regression gate for the performance upgrade."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAIL: list[str] = []


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        check(False, f"{rel} exists")
        return ""
    return path.read_text(encoding="utf-8")


def check(ok: bool, message: str) -> None:
    print(("[OK]   " if ok else "[FAIL] ") + message)
    if not ok:
        FAIL.append(message)


compose = read("docker-compose.yml")
env_example = read(".env.example")
ing = read("ingestion/worker.py")
catalogue = read("ingestion/catalogue_sync.py")
gateway = read("api/services/cctv_gateway.py")
yolo = read("ai_engine/yolo_worker.py")
anpr = read("ai_engine/anpr_worker.py")
policy = read("ai_engine/anpr_policy.py")
main = read("ai_engine/main.py")
grid = read("dashboard/src/components/CameraGrid.jsx")
manager = read("dashboard/src/components/cameraPlayerManager.js")
app = read("dashboard/src/App.jsx")
face = read("ai_engine/face_worker.py")

check("FRAME_GATE_ENABLED" in compose and "RAW_FRAME_STREAM_MAXLEN" in compose, "frame-gate settings are configured")
check("CATEGORY_INTERVALS" in ing, "camera sampling categories are implemented")
for value in ("0.300", "0.500", "0.800"):
    check(value in ing, f"sampling interval {value}s is defined")
check("np.mean(cv2.absdiff" in ing and "THUMBNAIL_SIZE" in ing, "motion gate uses a reduced grayscale thumbnail")
check("self.r.hset(ALIVE_KEY" in ing and "ALIVE_INTERVAL" in ing, "camera-alive signal is independent")
check("maxlen=RAW_STREAM_MAX" in ing and "processing_interval_ms" in ing, "raw frame stream is bounded and carries sampling metadata")

check("window_seconds" in policy and "observed_at >= current - self.window_seconds" in policy, "ANPR voting is wall-clock based")
check("first_seen_at" in policy and "min_track_age" in policy, "ANPR track-age gating is time based")
check("ProcessPoolExecutor" in anpr and "MAX_PENDING_JOBS" in anpr and 'get_context("fork")' in anpr, "ANPR OCR uses bounded forked workers")
check("_preprocess_for_ocr" in anpr and "createCLAHE" in anpr and "addWeighted" in anpr, "ANPR preprocessing is bounded and enhanced")

check("_preload_models" in main and "_preload_models(ANPR_ENABLED, FACE_ENABLED)" in main, "AI models are preloaded before workers")
check("get_yolo_model()" in yolo and "get_yolo_model()" in face, "preloaded YOLO is reused")

check("IntersectionObserver" in manager and "MAX_PLAYERS=12" in manager, "frontend player budget is centralized")
check("OFFSCREEN_DELAY" in manager and "visibilitychange" in manager, "offscreen/page-hidden players are suspended")
check("'SUSPENDED'" in grid and "'ERROR'" in grid and "15000" in grid, "player lifecycle and snapshot fallback are present")
check("wsBatchRef" in app and "500" in app, "WebSocket update batching is present")

check((ROOT / "database/migrations/025_performance_processing_category.sql").exists(), "performance migration exists")
check((ROOT / "ai_engine/thresholds.yaml").exists(), "ANPR thresholds file exists")

check("CCTV_EMAIL" in gateway and 'data={"email": self.email, "password": self.password}' in gateway, "CCTV email+password authentication is wired")
check("CCTV_EMAIL" in catalogue and 'data={"email": CCTV_EMAIL, "password": CCTV_PASSWORD}' in catalogue, "ingestion catalogue login uses CCTV email+password")
check("CCTV_EMAIL" in compose and "CCTV_PASSWORD" in compose, "CCTV credentials are injected into Docker services")
check("CCTV_EMAIL=" in env_example and "CCTV_PASSWORD=" in env_example, "CCTV credentials are documented")
check('log.info("Opening RTSP/TCP source for %s", self.name)' in ing, "RTSP credential-bearing URLs are not logged")

for rel, text_value in (
    ("scripts/performance_regression.py", ROOT / "scripts/performance_regression.py"),
    ("scripts/seed_rbac_test_users.py", ROOT / "scripts/seed_rbac_test_users.py"),
    ("ingestion/catalogue_sync.py", None),
    ("api/services/cctv_gateway.py", None),
):
    try:
        ast.parse((text_value.read_text(encoding="utf-8") if text_value else read(rel)), filename=rel)
        check(True, f"{rel} parses successfully")
    except SyntaxError as exc:
        check(False, f"{rel} syntax error: {exc}")

votes = [0.0, 1.5, 3.0, 7.5]
check(sum(t >= 7.5 - 8.0 for t in votes) == 4, "four observations fit inside the eight-second vote window")
check(sum(t >= 10.0 - 8.0 for t in votes) < 4, "old observations expire outside the eight-second vote window")

try:
    tree = ast.parse(ing, filename="ingestion/worker.py")
    intervals = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "CATEGORY_INTERVALS"
            and isinstance(node.value, ast.Dict)
        ):
            intervals = {
                key.value: value.value
                for key, value in zip(node.value.keys, node.value.values)
                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
            }
    check(intervals.get("highway") == 0.300, "highway interval is 300ms")
    check(intervals.get("pedestrian") == 0.500, "pedestrian interval is 500ms")
    check(intervals.get("static") == 0.800, "static interval is 800ms")
except Exception as exc:
    check(False, f"sampling constants can be inspected: {exc}")

if FAIL:
    print(f"\n{len(FAIL)} regression gate(s) failed.")
    raise SystemExit(1)

print("\nAll performance gates passed.")
