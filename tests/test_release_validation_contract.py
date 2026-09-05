from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_release_gates_match_current_repository():
    ci=(ROOT/"scripts/final_ci_gate.py").read_text(encoding="utf-8")
    integ=(ROOT/"scripts/final_integration_gate.py").read_text(encoding="utf-8")
    val=(ROOT/"scripts/validate_refactor.py").read_text(encoding="utf-8")
    wf=(ROOT/".github/workflows/p0-release-gate.yml").read_text(encoding="utf-8")
    assert "api/routes/test.py" in ci and "api/routes/test_alerts.py" not in ci
    assert "api/routes/test.py" in integ and "api/routes/test_alerts.py" not in integ
    assert "api/routes/test.py" in val
    assert "repository-contract:" in wf and "dashboard-build:" in wf and "compose-validation:" in wf
