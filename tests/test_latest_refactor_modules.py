#!/usr/bin/env python3
"""Regression coverage for the latest Sentinel refactors and feature additions.

These tests are intentionally source-level contracts for deployment-sensitive
modules. They catch broken exports, route mismatches, accidental production
coupling, state-loss regressions, and feed lifecycle omissions before runtime.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dashboard_api_client_exports_api_and_latest_test_feed_operations():
    source = read("dashboard/src/api/client.js")
    assert re.search(r"export\s+const\s+api\s*=", source)
    assert "getAuthConfig:()=>req('/auth/config')" in source
    assert "getTestAssets:()=>req('/test/assets')" in source
    assert "removeTestVideo:" in source
    assert "removeTestFeed:" in source
    assert "addTestFeed:" in source


def test_auth_config_is_bootstrap_safe_and_database_independent():
    source = read("api/routes/auth.py")
    match = re.search(
        r"@router\.get\('/config'\)(.*?)(?=\n@router\.post\('/login')",
        source,
        re.DOTALL,
    )
    assert match, "auth config route is missing"
    block = match.group(1)
    assert "async def config()" in block
    assert "Depends(get_db)" not in block
    assert "AUTH_REQUIRED" in block
    assert "TEST_ENDPOINT_ENABLED" in block
    assert "session_persistent" in block


def test_production_hls_uses_same_origin_authenticated_path():
    models = read("api/models.py")
    dashboard = read("dashboard/src/components/CameraGrid.jsx")
    assert '"/api/cctv/' in models or '"/api/cctv/{' in models
    assert "/api/cctv/cam" in dashboard
    assert "cctv.corp8.cloud" not in dashboard


def test_cctv_proxy_has_credentialed_cors_contract():
    source = read("api/routes/cctv.py")
    assert "Access-Control-Allow-Origin" in source
    assert "Access-Control-Allow-Credentials" in source
    assert "Vary" in source
    assert "await asyncio.to_thread(gateway.proxy_asset, asset_path)" in source
    assert "await db.close()" in source
    assert '"*"' not in source[source.find("Access-Control-Allow-Origin") - 100: source.find("Access-Control-Allow-Origin") + 250]


def test_test_feed_asset_lifecycle_is_complete():
    source = read("api/routes/test.py")
    assert '@router.get("/assets")' in source
    assert '@router.delete("/assets/{asset_id}")' in source
    assert '@router.post("/sessions/{session_id}/feeds"' in source
    assert '@router.delete("/sessions/{session_id}/feeds/{stream_id}")' in source
    assert "DELETE FROM test_session_feeds WHERE asset_id" in source
    assert "DELETE FROM test_video_assets WHERE id" in source
    assert "test:remove_feed:" in source
    assert "_close_empty_session" in source
    delete_start = source.find('@router.delete("/assets/{asset_id}")')
    delete_end = source.find('@router.delete("/sessions/{session_id}/feeds/', delete_start)
    block = source[delete_start:delete_end]
    assert "path.unlink" in block
    assert "Test video cannot be permanently removed" in block


def test_test_feed_state_and_ui_management_are_connected():
    app = read("dashboard/src/App.jsx")
    grid = read("dashboard/src/components/CameraGrid.jsx")
    modal = read("dashboard/src/components/TestDiagnosticsModal.jsx")
    navbar = read("dashboard/src/components/Navbar.jsx")

    assert "TEST_CAMERAS_KEY" in app
    assert "PRODUCTION_CAMERAS_KEY" in app
    assert "onManageTestFeeds" in app
    assert "onRemoveTestFeed" in app
    assert "testMode=false,onManageTestFeeds" in grid
    assert "test-feed-add-button" in grid
    assert "TEST_SELECTION_KEY" in modal
    assert "removeAsset" in modal
    assert "addTestFeed" in modal
    assert "Test Video Library" not in navbar


def test_ingestion_runner_supports_per_feed_lifecycle():
    source = read("ingestion/test_runner.py")
    assert "test:remove_feed:" in source
    assert "publishers" in source and "{}, 0" in source
    assert "publishers.pop(" in source
    assert "os.killpg(process.pid" in source
    assert "if not feeds:" in source


def test_test_video_storage_is_writable_for_asset_management():
    compose = read("docker-compose.yml")
    api_start = compose.find("  api:")
    api_end = compose.find("\n  mediamtx:", api_start)
    api = compose[api_start:api_end]
    assert "./videos:/videos" in api
    assert "./videos:/videos:ro" not in api
    assert "test_videos:/test_videos" in api


def test_camera_state_refresh_does_not_intentionally_replace_state_with_empty_defaults():
    source = read("dashboard/src/App.jsx")
    assert "readCachedJson(PRODUCTION_CAMERAS_KEY,[])" in source
    assert "writeCachedJson(PRODUCTION_CAMERAS_KEY,cams)" in source
    assert "readCachedJson(TEST_CAMERAS_KEY,[])" in source
    assert "writeCachedJson(TEST_CAMERAS_KEY,tc)" in source


def test_latest_camera_player_avoids_snapshot_as_the_live_production_source():
    source = read("dashboard/src/components/CameraGrid.jsx")
    assert "const visibleImage=!live && snapshot && state==='ERROR'" in source
    assert "configured.startsWith('/api/cctv/')" in source
    assert "},[sourceUrl])" in source
    assert "},[])" in source
    assert "hls.recoverMediaError()" in source
    assert "hls.startLoad()" in source
    assert "hlsRef.current.destroy()" in source


def test_test_session_header_and_exit_cleanup_follow_the_current_contract():
    client = read("dashboard/src/api/client.js")
    app = read("dashboard/src/App.jsx")
    assert "'X-Test-Session-Id':testSession" in client
    assert "sentinel_test_session" in app
    assert "await api.closeTestSession(sessionId)" in app


def test_expired_saved_session_does_not_present_as_an_api_outage():
    source = read("dashboard/src/App.jsx")
    assert "catch{if(active){writeAuthToken(null);setPrincipal(null);setAuthReady(true);setAuthError('')}}" in source


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
