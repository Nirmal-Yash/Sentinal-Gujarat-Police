from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_test_runner_can_stop_one_feed_without_stopping_the_session():
    source = (ROOT / "ingestion" / "test_runner.py").read_text(encoding="utf-8")
    assert "test:remove_feed:{session_id}:*" in source
    assert "publishers.pop(removed_stream, None)" in source
    assert "os.killpg(process.pid, signal.SIGTERM)" in source
    assert "if not feeds:" in source


def test_test_runner_uses_low_latency_test_stream_encoding():
    source = (ROOT / "ingestion" / "test_runner.py").read_text(encoding="utf-8")
    assert '"-preset","ultrafast"' in source
    assert '"-tune","zerolatency"' in source
    assert '"-g","30"' in source
