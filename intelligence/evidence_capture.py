"""Create immutable, human-readable evidence for an alert."""
from __future__ import annotations

import base64, hashlib, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

try:
    from .secure_storage import write_protected
except ImportError:
    from secure_storage import write_protected

EVIDENCE_ROOT = Path(os.getenv("EVIDENCE_STORAGE_PATH", os.getenv("EVIDENCE_ROOT", "/evidence")))
MAX_SNAPSHOT_BYTES = int(os.getenv("MAX_EVIDENCE_BYTES", str(4 * 1024 * 1024)))
THUMB_MAX = (320, 240)


def _bbox(det):
    value = det.get("bbox") if isinstance(det, dict) else None
    if isinstance(value, dict):
        value = [value.get(k) for k in ("x1", "y1", "x2", "y2")]
    if value is None and isinstance(det, dict):
        value = [det.get(k) for k in ("x1", "y1", "x2", "y2")]
    try:
        x1, y1, x2, y2 = [int(float(v)) for v in value]
        return x1, y1, x2, y2
    except (TypeError, ValueError):
        return None


def _annotate(image, detections, alert_type, camera_name, captured_at):
    """Return annotated full image bytes and dimensions; preserve raw bytes if decoding fails."""
    try:
        import cv2
        import numpy as np
        decoded = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            return image, None, None, 0
        height, width = decoded.shape[:2]
        colors = {"person": (255, 200, 0), "person_running": (0, 60, 255), "vehicle": (0, 200, 100), "plate": (255, 255, 0)}
        count = 0
        for det in detections or []:
            box = _bbox(det)
            if not box:
                continue
            x1, y1, x2, y2 = box
            x1, y1 = max(0, min(width - 1, x1)), max(0, min(height - 1, y1))
            x2, y2 = max(x1 + 1, min(width, x2)), max(y1 + 1, min(height, y2))
            label = str(det.get("plate_text") or det.get("label") or det.get("detection_type") or "detection").replace("_", " ").upper()
            color = colors.get(str(det.get("label") or det.get("detection_type") or "").lower(), (200, 200, 200))
            cv2.rectangle(decoded, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, .5, 1)
            top = max(th + 8, y1)
            cv2.rectangle(decoded, (x1, top - th - 8), (min(width, x1 + tw + 6), top), color, -1)
            cv2.putText(decoded, label, (x1 + 3, top - 4), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 0), 1, cv2.LINE_AA)
            count += 1
        stamp = datetime.fromtimestamp(captured_at, timezone.utc).strftime("%d %b %Y  %H:%M:%S UTC")
        overlay = decoded.copy(); cv2.rectangle(overlay, (0, 0), (width, 34), (0, 0, 0), -1); cv2.addWeighted(overlay, .62, decoded, .38, 0, decoded)
        cv2.putText(decoded, str(camera_name or "Camera")[:64], (8, 23), cv2.FONT_HERSHEY_SIMPLEX, .58, (255, 200, 0), 1, cv2.LINE_AA)
        cv2.putText(decoded, stamp, (max(8, width - 190), 23), cv2.FONT_HERSHEY_SIMPLEX, .42, (220, 220, 220), 1, cv2.LINE_AA)
        footer = str(alert_type or "Alert").replace("_", " ").upper()[:48]
        overlay = decoded.copy(); cv2.rectangle(overlay, (0, height - 28), (width, height), (0, 0, 0), -1); cv2.addWeighted(overlay, .62, decoded, .38, 0, decoded)
        cv2.putText(decoded, footer, (8, height - 9), cv2.FONT_HERSHEY_SIMPLEX, .48, (0, 80, 255), 1, cv2.LINE_AA)
        ok, encoded = cv2.imencode(".jpg", decoded, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not ok:
            return image, width, height, count
        return encoded.tobytes(), width, height, count
    except Exception:
        return image, None, None, 0


def capture_snapshot_bundle(redis_client, camera_id: str, alert_id: str, captured_at: float, *, detections=None, alert_type="Alert", camera_name=None) -> Optional[dict]:
    data = redis_client.get(f"snapshot:{camera_id}")
    if not data:
        return None
    if isinstance(data, str):
        data = data.encode()
    try:
        source = base64.b64decode(data, validate=True)
    except Exception:
        return None
    if not source or len(source) > MAX_SNAPSHOT_BYTES:
        return None
    image, width, height, count = _annotate(source, detections, alert_type, camera_name or camera_id, captured_at)
    digest = hashlib.sha256(image).hexdigest()
    day = datetime.fromtimestamp(captured_at, timezone.utc).strftime("%Y/%m/%d")
    key = f"alerts/{day}/{alert_id}.jpg"
    thumb_key = f"alerts/{day}/{alert_id}_thumb.jpg"
    target, thumb_target = EVIDENCE_ROOT / key, EVIDENCE_ROOT / thumb_key
    stored = write_protected(target, image)
    thumbnail = image
    try:
        import cv2, numpy as np
        decoded = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is not None:
            h, w = decoded.shape[:2]; scale = min(THUMB_MAX[0] / max(1, w), THUMB_MAX[1] / max(1, h), 1.0)
            thumbnail = cv2.imencode(".jpg", cv2.resize(decoded, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA), [int(cv2.IMWRITE_JPEG_QUALITY), 78])[1].tobytes()
    except Exception:
        pass
    stored_thumb = write_protected(thumb_target, thumbnail)
    return {"stored_path": str(stored), "storage_key": key, "thumbnail_path": str(stored_thumb), "thumbnail_key": thumb_key, "sha256": digest, "frame_width": width, "frame_height": height, "detections_count": count, "description": "Annotated frame showing detected objects and alert context."}


def capture_snapshot(redis_client, camera_id: str, alert_id: str, captured_at: float) -> Optional[Tuple[str, str, str]]:
    """Backward-compatible tuple API used by existing workers/tests."""
    bundle = capture_snapshot_bundle(redis_client, camera_id, alert_id, captured_at)
    return (bundle["stored_path"], bundle["storage_key"], bundle["sha256"]) if bundle else None


def build_human_summary(alert_type: str, detection_data: dict, camera_name: str) -> str:
    plate = detection_data.get("plate_text") or detection_data.get("normalized_plate")
    if "watchlist" in str(alert_type).lower():
        return f"Watchlist target identified at {camera_name}. {('Plate: ' + plate) if plate else 'Person match detected'}."
    if "plate" in str(alert_type).lower():
        return f"Vehicle {plate or 'with an unreadable plate'} sighted at {camera_name}."
    if "running" in str(alert_type).lower():
        return f"Rapid movement detected at {camera_name}; possible running crowd incident."
    if "crowd" in str(alert_type).lower():
        return f"Unusual crowd activity detected at {camera_name}."
    if "person" in str(alert_type).lower() or "face" in str(alert_type).lower():
        return f"Person of interest identified at {camera_name}."
    return f"{str(alert_type or 'Alert').replace('_', ' ').capitalize()} detected at {camera_name}."
