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

def test_cctv_credentials_use_email_and_password_server_side():
    gateway = (ROOT / "api" / "services" / "cctv_gateway.py").read_text(encoding="utf-8")
    catalogue = (ROOT / "ingestion" / "catalogue_sync.py").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert 'os.getenv("CCTV_EMAIL", "").strip()' in gateway
    assert 'data={"email": self.email, "password": self.password}' in gateway
    assert 'CCTV_EMAIL = os.getenv("CCTV_EMAIL", "").strip()' in catalogue
    assert 'data={"email": CCTV_EMAIL, "password": CCTV_PASSWORD}' in catalogue
    assert 'CCTV_EMAIL=${CCTV_EMAIL:?CCTV_EMAIL must be supplied}' in compose
    assert 'CCTV_EMAIL=replace-with-assigned-feed-email' in env

def test_catalogue_writes_processing_category_with_canonical_hls():
    catalogue = (ROOT / "ingestion" / "catalogue_sync.py").read_text(encoding="utf-8")
    assert 'processing_fps_category=EXCLUDED.processing_fps_category' in catalogue
    assert 'hls = f"/api/cctv/{canonical}/index.m3u8"' in catalogue