"""Stream-source adapter seam; OpenCV/RTSP remains the only active adapter.

New protocols must implement ``open`` without changing CameraWorker's event,
health, retry, or Redis behavior.  Adapters may be selected from registry
metadata only after their credentials and capability contract are approved.
"""
from abc import ABC, abstractmethod
import os
from urllib.parse import quote, urlsplit, urlunsplit

import cv2


def _credentialed_rtsp_url(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    if parts.scheme.lower() != "rtsp" or parts.username or parts.password:
        return str(url)
    email = os.getenv("CCTV_EMAIL", "").strip()
    password = os.getenv("CCTV_PASSWORD", "")
    if not email or password == "":
        raise RuntimeError("CCTV RTSP credentials are not configured")
    host = parts.hostname or ""
    port = ":" + str(parts.port) if parts.port else ""
    auth = quote(email, safe="") + ":" + quote(password, safe="") + "@" + host + port
    return urlunsplit((parts.scheme, auth, parts.path, parts.query, parts.fragment))


class StreamAdapter(ABC):
    """Minimal source boundary for RTSP, ONVIF, HLS, WHEP, and vendor adapters."""

    @abstractmethod
    def open(self) -> cv2.VideoCapture:
        """Return an opened capture object; callers own reconnect/release."""


class OpenCVRTSPAdapter(StreamAdapter):
    """Current production behavior preserved behind the adapter boundary."""

    def __init__(self, url: str):
        self.url = _credentialed_rtsp_url(url)

    def open(self) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        return capture


def adapter_for(camera: dict) -> StreamAdapter:
    """Factory extension point; deliberately fails closed for unimplemented sources.

    ``camera`` is the canonical registry record.  Future adapters can use its
    protocol/source-system fields, but source credentials must never leave the
    ingestion process or be exposed through the dashboard API.
    """
    url = camera.get("rtsp_url")
    if not url:
        raise ValueError(f"Camera {camera.get('id', '<unknown>')} has no RTSP source")
    return OpenCVRTSPAdapter(url)
