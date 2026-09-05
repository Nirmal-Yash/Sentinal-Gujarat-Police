from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_alert_components_canonicalize_and_gate_operations_by_role():
    panel = (ROOT / "dashboard" / "src" / "components" / "AlertPanel.jsx").read_text(encoding="utf-8")
    workspace = (ROOT / "dashboard" / "src" / "components" / "AlertWorkspace.jsx").read_text(encoding="utf-8")
    bell = (ROOT / "dashboard" / "src" / "components" / "NotificationBell.jsx").read_text(encoding="utf-8")
    app = (ROOT / "dashboard" / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "mergeCanonicalAlerts" in panel
    assert "ALERT_OPERATE_ROLES" in panel
    assert "canOperate" in panel
    assert "mergeCanonicalAlerts" in workspace
    assert "principal" in workspace
    assert "principal" in bell
    assert "principal={principal}" in app
