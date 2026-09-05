#!/usr/bin/env python3
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]; failures=[]
def r(p):
 q=ROOT/p
 if not q.is_file(): failures.append(f"missing: {p}"); return ""
 return q.read_text(encoding="utf-8")
def c(ok,msg):
 print(f"[{'OK' if ok else 'FAIL'}] {msg}")
 if not ok: failures.append(msg)
def main():
 a=r("api/auth.py"); c(all(x in a for x in ("VIEWER","OPERATOR","INVESTIGATOR","AUDITOR","ADMIN","SUPERADMIN")),"RBAC roles")
 c(all(x in a for x in ("camera:read","camera:write","alert:read","alert:operate","search:read","evidence:read","evidence:create","registry:admin","audit:read","system:admin")),"RBAC capabilities")
 g=r("api/services/cctv_gateway.py"); h=r("api/routes/cctv.py"); c("CCTV_EMAIL" in g and "CCTV_PASSWORD" in g and "_verify_playback_token" in h,"authenticated CCTV proxy and provider credentials")
 ap=r("dashboard/src/App.jsx"); gr=r("dashboard/src/components/CameraGrid.jsx"); pm=r("dashboard/src/components/cameraPlayerManager.js"); c("PRODUCTION_CAMERAS_KEY" in ap and "TEST_CAMERAS_KEY" in ap,"domain-separated dashboard state"); c("useCameraPlayerSlot" in gr and "IntersectionObserver" in pm,"bounded camera playback")
 t=r("api/routes/test.py"); tr=r("ingestion/test_runner.py"); ui=r("dashboard/src/components/TestFeedManager.jsx"); c('@router.post("/sessions/{session_id}/feeds"' in t and '@router.delete("/sessions/{session_id}/feeds/{stream_id}")' in t,"Test Feed API"); c("test:remove_feed:" in tr and "_start_feed" in tr and "_stop_feed" in tr,"Test Feed runtime"); c("api.addTestFeed" in ui and "api.uploadTestVideo" in ui,"Test Feed UI")
 an=r("ai_engine/anpr_worker.py"); su=r("ai_engine/main.py"); be=r("ai_engine/behavior_worker.py"); c("ProcessPoolExecutor" in an and "MAX_PENDING_JOBS" in an and "VOTE_WINDOW_SECS" in an and "TRACK_MIN_AGE" in an,"ANPR bounded consensus"); c("_preload_models" in su and "set_yolo_model" in su and "set_ocr_reader" in su,"shared AI model preload"); c("person_count < CROWD_MIN_PERSONS" in be,"person-aware crowd gating")
 ing=r("ingestion/worker.py"); cat=r("ingestion/catalogue_sync.py"); c("FRAME_GATE_ENABLED" in ing and "ALIVE_KEY" in ing and "RAW_STREAM_MAX" in ing and "processing_fps_category" in ing,"ingestion runtime contract"); c("CCTV_EMAIL" in cat and "processing_fps_category" in cat,"catalogue contract")
 al=r("api/routes/alerts.py"); panel=r("dashboard/src/components/AlertPanel.jsx"); work=r("dashboard/src/components/AlertWorkspace.jsx"); c("VALID_TRANSITIONS" in al and 'has_permission(principal, "alert:operate")' in al,"alert API lifecycle and authorization"); c("mergeCanonicalAlerts" in panel and "ALERT_OPERATE_ROLES" in panel and "mergeCanonicalAlerts" in work,"alert UI contract")
 se=r("api/routes/search.py"); c("X-Test-Session-Id" in se and "test:person:investigations" in se,"isolated person investigation routing")
 mo=r("api/models.py"); regr=r("dashboard/src/components/CameraRegistryModal.jsx"); c('pattern="^(highway|pedestrian|static)$"' in mo and 'name="processing_fps_category"' in regr,"registry category contract")
 co=r("docker-compose.yml"); ev=r(".env.example"); c("CCTV_EMAIL=" in ev and "CCTV_PASSWORD=" in ev,"environment documentation"); c("test_person_investigation:" in co and "test_ai_worker:" in co and "test_intelligence:" in co,"isolated Test services"); c("ANPR_OCR_WORKERS" in co and "ANPR_MAX_PENDING_JOBS" in co,"ANPR deployment controls")
 try:
  tracked=subprocess.run(["git","ls-files"],cwd=ROOT,check=True,text=True,capture_output=True).stdout.splitlines(); c(".env" not in tracked,".env not tracked"); c(not any(x.endswith(".pyc") or "__pycache__/" in x for x in tracked),"compiled artifacts not tracked")
 except Exception as exc: c(False,f"git hygiene: {exc}")
 if failures: print(f"\nVALIDATE_REFACTOR=FAIL ({len(failures)} failures)"); return 1
 print("\nVALIDATE_REFACTOR=PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
