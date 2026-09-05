from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auth_config_is_database_independent_bootstrap_endpoint():
    source = (ROOT / "api" / "routes" / "auth.py").read_text(encoding="utf-8")
    start = source.index("@router.get('/config')")
    end = source.index("@router.post('/login')", start)
    block = source[start:end]
    assert "async def config()" in block
    assert "Depends(get_db)" not in block
    assert "bootstrap_admin_configured" in block
    assert "test_enabled" in block
