from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_dashboard_reference_navigation_and_diagnostics_contract():
    login=(ROOT/"dashboard/src/components/LoginModal.jsx").read_text(encoding="utf-8")
    nav=(ROOT/"dashboard/src/components/Navbar.jsx").read_text(encoding="utf-8")
    diag=(ROOT/"dashboard/src/components/TestDiagnosticsModal.jsx").read_text(encoding="utf-8")
    alerts=(ROOT/"dashboard/src/components/alerts/alerts.css").read_text(encoding="utf-8")
    theme=(ROOT/"dashboard/src/theme.css").read_text(encoding="utf-8")
    app=(ROOT/"dashboard/src/App.jsx").read_text(encoding="utf-8")
    assert "Unauthorized operator access" in login or "Authorized operator access" in login
    assert "routeAllowed" in nav
    assert "ROLE_RANK" in nav
    assert "TEST_MAX_UPLOAD_BYTES" in diag or "MAX_VIDEO_SIZE_BYTES" in diag
    assert "Acknowledge & Import" in diag or "Isolated video test mode" in diag
    assert "AlertStatusBadge" in alerts or "alert-" in alerts
    assert 'html[data-theme="light"]' in theme
    assert "color-scheme: light" in theme
    assert "principal={principal}" in app
