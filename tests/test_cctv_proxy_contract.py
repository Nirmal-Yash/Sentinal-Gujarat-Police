from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cctv_proxy_uses_authenticated_same_origin_hls_and_credentialed_cors():
    source = (ROOT / "api" / "routes" / "cctv.py").read_text(encoding="utf-8")
    assert 'dependencies=[Depends(require_permission("camera:read"))]' in source
    assert "await asyncio.to_thread(gateway.proxy_asset, asset_path)" in source
    assert "await db.close()" in source
    assert "Access-Control-Allow-Origin" in source
    assert "Access-Control-Allow-Credentials" in source
    assert "Vary" in source
    assert '"Access-Control-Allow-Origin": "*"' not in source


def test_dashboard_canonicalizes_production_hls_to_same_origin_proxy():
    source = (ROOT / "dashboard" / "src" / "api" / "client.js").read_text(encoding="utf-8")
    assert "startsWith('/api/cctv/')" in source
    assert "hls_url:`/api/cctv/${providerId}/index.m3u8`" in source
    assert "https://cctv.corp8.cloud/${providerId}/index.m3u8" not in source
