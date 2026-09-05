def test_person_investigation_worker_uses_namespaced_streams():
    from pathlib import Path
    source = Path("ai_engine/person_investigation_worker.py").read_text(encoding="utf-8")
    assert 'TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"' in source
    assert 'STREAM = f"{PREFIX}person:investigations"' in source
    assert 'GROUP = f"{PREFIX}person_investigation_workers"' in source
    assert 'IMAGE_PREFIX = f"{PREFIX}person:image:"' in source


def test_person_investigation_api_routes_test_requests_to_test_namespace():
    from pathlib import Path
    source = Path("api/routes/search.py").read_text(encoding="utf-8")
    assert "async def _run_person_analysis(payload: bytes, timeout: float, operation: str, test_mode: bool = False)" in source
    assert "'validate', session_uuid is not None" in source
    assert "'investigate', session_uuid is not None" in source
    assert "stream = f'{prefix}person:investigations'" in source
