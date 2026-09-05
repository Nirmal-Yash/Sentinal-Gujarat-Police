from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_test_feed_lifecycle_isolated_and_role_protected():
    source = (ROOT / "api" / "routes" / "test_feeds.py").read_text(encoding="utf-8")
    assert 'router = APIRouter(prefix="/test"' in source
    assert 'Depends(require_role("ADMIN"))' in source
    assert 'POSTGRES' not in source
    assert "test_session_feeds" in source
    assert "test:remove_feed:" in source
    assert "production_data_affected" in source


def test_test_feed_routes_are_registered_without_replacing_the_existing_test_router():
    source = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
    assert "test_feeds" in source
    assert "app.include_router(test_feeds.router)" in source
