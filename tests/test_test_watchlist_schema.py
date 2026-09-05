from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_test_watchlist_schema_is_session_scoped():
    schema=(ROOT/"database/migrations/026_test_watchlists.sql").read_text(encoding="utf-8")
    route=(ROOT/"api/routes/test.py").read_text(encoding="utf-8")
    assert "REFERENCES test_sessions(id) ON DELETE CASCADE" in schema
    assert "test_watchlists" in route
    assert "production_data_affected" in route
    assert "FROM watchlist" not in route[route.find('class TestWatchlistCreate'):route.find('@router.post(\"/sessions\", status_code=201)')]
