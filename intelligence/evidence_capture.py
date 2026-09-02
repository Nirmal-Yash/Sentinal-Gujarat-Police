"""Capture immutable alert evidence from the latest camera snapshot."""
from __future__ import annotations
import base64, hashlib, os
from pathlib import Path
from typing import Optional, Tuple
from secure_storage import write_protected

EVIDENCE_ROOT = Path(os.getenv("EVIDENCE_STORAGE_PATH", os.getenv("EVIDENCE_ROOT", "/evidence")))
MAX_SNAPSHOT_BYTES = int(os.getenv("MAX_EVIDENCE_BYTES", str(4 * 1024 * 1024)))

def capture_snapshot(redis_client, camera_id: str, alert_id: str, captured_at: float) -> Optional[Tuple[str, str, str]]:
    data = redis_client.get(f"snapshot:{camera_id}")
    if not data: return None
    if isinstance(data, str): data = data.encode()
    try: image = base64.b64decode(data, validate=True)
    except Exception: return None
    if not image or len(image) > MAX_SNAPSHOT_BYTES: return None
    digest = hashlib.sha256(image).hexdigest()
    day = __import__("datetime").datetime.fromtimestamp(captured_at, __import__("datetime").timezone.utc).strftime("%Y/%m/%d")
    key = f"alerts/{day}/{alert_id}.jpg"
    target = EVIDENCE_ROOT / key
    stored = write_protected(target, image)
    return str(stored), key, digest
