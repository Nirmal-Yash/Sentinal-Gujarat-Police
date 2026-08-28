import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidence_capture import capture_snapshot


class FakeRedis:
    def __init__(self, payload):
        self.payload = payload

    def get(self, key):
        return self.payload


class EvidenceCaptureTests(unittest.TestCase):
    def test_capture_is_content_addressed_and_bounded(self):
        image = b"\xff\xd8\xffsynthetic-jpeg\xff\xd9"
        redis_client = FakeRedis(base64.b64encode(image))
        expected_hash = hashlib.sha256(image).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            with patch("evidence_capture.EVIDENCE_ROOT", Path(root)):
                captured = capture_snapshot(redis_client, "cam-1", "alert-1", 1756382400)
                self.assertIsNotNone(captured)
                path, key, digest = captured
                self.assertEqual(digest, expected_hash)
                self.assertEqual(key, "alerts/2025/08/28/alert-1.jpg")
                self.assertEqual(Path(path).read_bytes(), image)

    def test_missing_snapshot_returns_none(self):
        with patch("evidence_capture.EVIDENCE_ROOT", Path(tempfile.gettempdir())):
            self.assertIsNone(capture_snapshot(FakeRedis(None), "cam-1", "alert-1", 1.0))


if __name__ == "__main__":
    unittest.main()
