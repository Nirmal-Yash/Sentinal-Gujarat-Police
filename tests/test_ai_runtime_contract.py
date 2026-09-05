from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_ai_supervisor_defines_shared_model_preload():
    source = (ROOT / "ai_engine" / "main.py").read_text(encoding="utf-8")
    assert "def _preload_models(load_anpr: bool)" in source
    assert "set_yolo_model(model)" in source
    assert "set_ocr_reader(reader)" in source
    assert "_preload_models(ANPR_ENABLED)" in source

def test_ai_workers_consume_shared_models_with_local_fallback():
    yolo = (ROOT / "ai_engine" / "yolo_worker.py").read_text(encoding="utf-8")
    face = (ROOT / "ai_engine" / "face_worker.py").read_text(encoding="utf-8")
    anpr = (ROOT / "ai_engine" / "anpr_worker.py").read_text(encoding="utf-8")
    assert "get_yolo_model() or YOLO(YOLO_MODEL)" in yolo
    assert 'get_yolo_model() or YOLO(os.getenv("YOLO_MODEL", "yolov8n.pt"))' in face
    assert 'get_ocr_reader() or easyocr.Reader' in anpr

def test_ai_threshold_contract_and_dependency_are_present():
    requirements = (ROOT / "ai_engine" / "requirements.txt").read_text(encoding="utf-8")
    thresholds = (ROOT / "ai_engine" / "thresholds.yaml").read_text(encoding="utf-8")
    assert "PyYAML==6.0.2" in requirements
    assert "vote_threshold:" in thresholds
    assert "ocr_cooldown_seconds:" in thresholds
    assert "preprocessing:" in thresholds

def test_anpr_policy_uses_time_window_and_track_age():
    policy = (ROOT / "ai_engine" / "anpr_policy.py").read_text(encoding="utf-8")
    assert "window_seconds" in policy
    assert "first_seen_at" in policy
    assert "min_track_age" in policy
    assert "observed_at >= current - self.window_seconds" in policy

def test_anpr_worker_bounds_ocr_work_and_preprocesses_plate_candidates():
    worker = (ROOT / "ai_engine" / "anpr_worker.py").read_text(encoding="utf-8")
    assert "ProcessPoolExecutor" in worker
    assert "MAX_PENDING_JOBS" in worker
    assert "pool.submit(_ocr_job, image_bytes)" in worker
    assert "_preprocess_for_ocr" in worker
    assert "TRACK_MIN_AGE" in worker
    assert "VOTE_WINDOW_SECS" in worker
