#!/usr/bin/env python3
from pathlib import Path
import re, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]; failures=[]
def read(p):
 q=ROOT/p
 if not q.is_file(): failures.append(f"missing: {p}"); return ""
 return q.read_text(encoding="utf-8")
def check(ok,msg):
 print(f"[{'OK' if ok else 'FAIL'}] {msg}")
 if not ok: failures.append(msg)
def main():
 required=[".env.example","docker-compose.yml","api/auth.py","api/routes/cctv.py","api/services/cctv_gateway.py","api/routes/cameras.py","api/routes/camera_imports.py","api/routes/test.py","api/routes/search.py","api/routes/alerts.py","api/routes/evidence.py","ai_engine/main.py","ai_engine/shared_models.py","ai_engine/yolo_worker.py","ai_engine/anpr_worker.py","ai_engine/anpr_policy.py","ai_engine/behavior_worker.py","ai_engine/face_worker.py","ai_engine/thresholds.yaml","ingestion/worker.py","ingestion/catalogue_sync.py","ingestion/test_runner.py","intelligence/alert_engine.py","intelligence/sighting_store.py","dashboard/src/App.jsx","dashboard/src/api/client.js","dashboard/src/components/CameraGrid.jsx","dashboard/src/components/cameraPlayerManager.js","dashboard/src/components/TestFeedManager.jsx","dashboard/src/components/AlertPanel.jsx","dashboard/src/components/AlertWorkspace.jsx","dashboard/src/components/NotificationBell.jsx","database/migrations/019_rbac_roles.sql","database/migrations/020_test_alert_lifecycle.sql","database/migrations/021_audit_integrity.sql","database/migrations/023_p1_intelligence_consistency.sql","database/migrations/024_stream_metadata_provenance.sql","database/migrations/025_processing_fps_category.sql","database/migrations/026_test_watchlists.sql"]
 for p in required: check((ROOT/p).is_file(),f"required component exists: {p}")
 versions=[m.group(1) for p in (ROOT/"database/migrations").glob("*.sql") if (m:=re.match(r"^(\d+)_",p.name))]
 check(len(versions)==len(set(versions)),"database migration numbers are unique")
 auth=read("api/auth.py")
 check(all(x in auth for x in ("VIEWER","OPERATOR","INVESTIGATOR","AUDITOR","ADMIN","SUPERADMIN")),"RBAC roles are declared")
 check(all(x in auth for x in ("camera:read","camera:write","alert:read","alert:operate","search:read","evidence:read","evidence:create","registry:admin","audit:read","system:admin")),"RBAC capabilities are declared")
 cctv=read("api/routes/cctv.py"); gateway=read("api/services/cctv_gateway.py")
 check("_verify_playback_token" in cctv and "principal_from_token" in cctv,"CCTV playback is authenticated")
 check("Access-Control-Allow-Credentials" in cctv and "Access-Control-Allow-Origin" in cctv,"CCTV proxy supports credentialed playback")
 check("CCTV_EMAIL" in gateway and "CCTV_PASSWORD" in gateway,"CCTV credentials are server-side")
 app=read("dashboard/src/App.jsx"); grid=read("dashboard/src/components/CameraGrid.jsx"); pm=read("dashboard/src/components/cameraPlayerManager.js")
 check("PRODUCTION_CAMERAS_KEY" in app and "TEST_CAMERAS_KEY" in app and "testMode?cameras:productionCameras" in app,"Production/Test dashboard state is separated")
 check("useCameraPlayerSlot" in grid and "IntersectionObserver" in pm,"camera playback is resource bounded")
 test_api=read("api/routes/test.py"); runner=read("ingestion/test_runner.py"); tui=read("dashboard/src/components/TestFeedManager.jsx")
 check('@router.post("/sessions/{session_id}/feeds"' in test_api and '@router.delete("/sessions/{session_id}/feeds/{stream_id}")' in test_api and '@router.delete("/assets/{asset_id}")' in test_api,"Test Feed lifecycle API is complete")
 check("test:remove_feed:" in runner and "_start_feed" in runner and "_stop_feed" in runner,"Test Feed runtime lifecycle is complete")
 check("api.addTestFeed" in tui and "api.uploadTestVideo" in tui and "api.removeTestVideo" in tui,"Test Feed UI is wired")
 anpr=read("ai_engine/anpr_worker.py"); sup=read("ai_engine/main.py"); behavior=read("ai_engine/behavior_worker.py")
 check("ProcessPoolExecutor" in anpr and "MAX_PENDING_JOBS" in anpr and "VOTE_WINDOW_SECS" in anpr and "TRACK_MIN_AGE" in anpr,"ANPR is bounded and consensus/track gated")
 check("_preload_models" in sup and "set_yolo_model" in sup and "set_ocr_reader" in sup,"AI model preload is centralized")
 check("person_count < CROWD_MIN_PERSONS" in behavior,"crowd anomalies are person gated")
 ing=read("ingestion/worker.py"); cat=read("ingestion/catalogue_sync.py")
 check("FRAME_GATE_ENABLED" in ing and "np.mean(cv2.absdiff" in ing and "ALIVE_KEY" in ing and "RAW_STREAM_MAX" in ing,"ingestion gating/heartbeat/bounds are present")
 check("processing_fps_category" in ing and "CCTV_EMAIL" in cat,"processing categories and CCTV auth reach ingestion")
 alerts=read("api/routes/alerts.py"); panel=read("dashboard/src/components/AlertPanel.jsx"); workspace=read("dashboard/src/components/AlertWorkspace.jsx")
 check("VALID_TRANSITIONS" in alerts and 'has_permission(principal, "alert:operate")' in alerts,"alert lifecycle is explicit and capability protected")
 check("mergeCanonicalAlerts" in panel and "ALERT_OPERATE_ROLES" in panel and "mergeCanonicalAlerts" in workspace,"alert UI is canonicalized and role aware")
 search=read("api/routes/search.py")
check("X-Test-Session-Id" in search and "prefix = 'test:' if test_mode else ''" in search and "person:investigations" in search,"person investigation Test routing is isolated")
 model=read("api/models.py"); registry=read("dashboard/src/components/CameraRegistryModal.jsx")
 check('pattern="^(highway|pedestrian|static)$"' in model and 'name="processing_fps_category"' in registry,"camera processing category is consistent")
 compose=read("docker-compose.yml"); env=read(".env.example")
 check("CCTV_EMAIL=" in env and "CCTV_PASSWORD=" in env,".env.example documents CCTV credentials")
    check("CCTV_EMAIL=${CCTV_EMAIL:?CCTV_EMAIL must be supplied}" in compose and "CCTV_PASSWORD=${CCTV_PASSWORD:?CCTV_PASSWORD must be supplied}" in compose,"Compose requires CCTV credentials")
 check("test_person_investigation:" in compose and "test_ai_worker:" in compose and "test_intelligence:" in compose,"Compose has isolated Test services")
 check("ANPR_OCR_WORKERS" in compose and "ANPR_MAX_PENDING_JOBS" in compose,"Compose exposes ANPR pool controls")
 contract_tests=list((ROOT/"tests").glob("test_*_contract.py"))
 check(len(contract_tests)>=7,"contract test suite is present")
 try:
  tracked=subprocess.run(["git","ls-files"],cwd=ROOT,check=True,text=True,capture_output=True).stdout.splitlines()
  check(".env" not in tracked,".env is not tracked")
  check(not any(p.endswith(".pyc") or "__pycache__/" in p for p in tracked),"compiled Python artifacts are not tracked")
 except Exception as exc: check(False,f"git hygiene check executes: {exc}")
 if failures:
  print(f"\nFINAL_CI_GATE=FAIL ({len(failures)} failures)"); return 1
 print("\nFINAL_CI_GATE=PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
