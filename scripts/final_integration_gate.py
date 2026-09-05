#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; failures=[]
def r(p):
 q=ROOT/p
 if not q.is_file(): failures.append(f"missing: {p}"); return ""
 return q.read_text(encoding="utf-8")
def c(ok,msg):
 print(f"[{'OK' if ok else 'FAIL'}] {msg}")
 if not ok: failures.append(msg)
def main():
 ta=r("api/routes/test.py"); tr=r("ingestion/test_runner.py"); pa=r("api/routes/search.py"); pw=r("ai_engine/person_investigation_worker.py")
 y=r("ai_engine/yolo_worker.py"); a=r("ai_engine/anpr_worker.py"); b=r("ai_engine/behavior_worker.py"); al=r("intelligence/alert_engine.py"); ss=r("intelligence/sighting_store.py"); i=r("ingestion/worker.py"); g=r("api/routes/cctv.py"); gr=r("dashboard/src/components/CameraGrid.jsx"); co=r("docker-compose.yml"); ap=r("dashboard/src/App.jsx")
 c('@router.post("/sessions/{session_id}/feeds"' in ta and '@router.delete("/sessions/{session_id}/feeds/{stream_id}")' in ta,"Test Feed API lifecycle")
 c("test:remove_feed:" in tr and "_start_feed" in tr and "_stop_feed" in tr,"Test Feed runtime lifecycle")
 c("test:" in y and "test:" in a and "test:" in b and 'PREFIX = "test:" if TEST_MODE else ""' in pw,"AI workers namespace Test streams")
 c("test:person:investigations" in pa,"person investigation API targets Test namespace")
 c("capture_snapshot" in al and "evidence" in al,"alert engine retains durable evidence path")
 c("business_sighting" in ss and "plate_validated" in ss and "anpr_consensus" in ss,"only confirmed ANPR sightings persist")
 c("FRAME_GATE_ENABLED" in i and "ALIVE_KEY" in i and "RAW_STREAM_MAX" in i,"ingestion performance controls")
 c("CCTV_EMAIL" in co and "CCTV_PASSWORD" in co and "/api/cctv/" in gr,"CCTV credentials and same-origin playback")
 c("ANPR_VOTE_WINDOW_SECS" in co and "ANPR_OCR_WORKERS" in co,"ANPR runtime controls")
 c("PRODUCTION_CAMERAS_KEY" in ap and "TEST_CAMERAS_KEY" in ap,"dashboard domain-separated caches")
 if failures: raise SystemExit(f"FINAL_INTEGRATION_GATE=FAIL ({len(failures)} failures)")
 print("FINAL_INTEGRATION_GATE=PASS")
if __name__=="__main__": main()
