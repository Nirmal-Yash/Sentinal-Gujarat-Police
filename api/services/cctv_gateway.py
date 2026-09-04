"""Authenticated gateway client for the current cctv.corp8.cloud infrastructure.

The CCTV provider uses a password-only form login that returns a session cookie.
The password remains server-side; browser clients never receive it.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Optional
from urllib.parse import urlparse

import requests

CCTV_BASE = "https://cctv.corp8.cloud"
LOGIN_PATH = "/auth/login"
CATALOGUE_PATH = "/cameras.json"


class CctvGateway:
    def __init__(self, password: str, base_url: str = CCTV_BASE, timeout: float = 15.0):
        self.password = password or ""
        self.base_url = base_url.rstrip("/")
        self.login_path = os.getenv("CCTV_LOGIN_PATH", LOGIN_PATH)
        self.catalogue_path = os.getenv("CCTV_CATALOGUE_PATH", CATALOGUE_PATH)
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "Sentinel-CCTV-Gateway/1.0"})
        self._lock = threading.RLock()
        self._authenticated_at = 0.0
        self._last_login_error: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.password)

    def _login_locked(self) -> None:
        if not self.password:
            raise RuntimeError("CCTV_PASSWORD is not configured")
        self._session.cookies.clear()
        login_url = f"{self.base_url}{self.login_path}"
        try:
            page = self._session.get(
                login_url,
                timeout=self.timeout,
                allow_redirects=True,
                headers={"Accept": "text/html,application/xhtml+xml,*/*"},
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"CCTV login page request failed: {exc}") from exc
        page.close()

        response = self._session.post(
            login_url,
            data={"password": self.password},
            headers={
                "Referer": login_url,
                "Origin": self.base_url,
                "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            },
            timeout=self.timeout,
            allow_redirects=True,
        )
        try:
            if response.status_code not in {200, 204}:
                raise RuntimeError(f"CCTV login failed with HTTP {response.status_code}")
            token = None
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    token = payload.get("access_token") or payload.get("token") or payload.get("jwt")
            except ValueError:
                pass
            if token:
                self._session.headers["Authorization"] = f"Bearer {token}"
            cookies = self._session.cookies.get_dict()
            if not cookies and not token:
                raise RuntimeError("CCTV login did not establish an authenticated session")
            self._authenticated_at = time.monotonic()
            self._last_login_error = None
        finally:
            response.close()

    def ensure_authenticated(self, force: bool = False) -> None:
        with self._lock:
            if not force and (time.monotonic() - self._authenticated_at) < 300 and self._session.cookies.get_dict():
                return
            try:
                self._login_locked()
            except Exception as exc:
                self._last_login_error = str(exc)
                raise

    def request(self, path: str, *, stream: bool = False) -> requests.Response:
        path = "/" + path.lstrip("/")
        self.ensure_authenticated()
        with self._lock:
            response = self._session.get(
                f"{self.base_url}{path}",
                timeout=self.timeout,
                allow_redirects=False,
                stream=stream,
            )
            if response.status_code in {401, 403}:
                response.close()
                self._login_locked()
                response = self._session.get(
                    f"{self.base_url}{path}",
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=stream,
                )
            if response.status_code in {302, 303}:
                location = response.headers.get("Location", "")
                response.close()
                raise RuntimeError(
                    f"CCTV upstream redirected authenticated request to {location or 'login'}"
                )
            return response

    def catalogue(self) -> list[dict]:
        response = self.request(self.catalogue_path)
        try:
            response.raise_for_status()
            payload = response.json()
        finally:
            response.close()
        if not isinstance(payload, list):
            raise RuntimeError("CCTV catalogue response is not a JSON array")
        cameras = [item for item in payload if isinstance(item, dict)]
        if not cameras:
            raise RuntimeError("CCTV catalogue returned no camera records")
        return cameras

    def hls_path_for(self, camera_id: str | int) -> str:
        text = str(camera_id).strip()
        suffix = text[3:] if text.lower().startswith("cam") else text
        if suffix.isdigit():
            suffix = suffix.zfill(2)
        return f"/cam{suffix}/index.m3u8"

    def proxy_asset(self, asset_path: str) -> requests.Response:
        path = "/" + asset_path.lstrip("/")
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc:
            raise ValueError("Absolute URLs are not allowed in CCTV proxy asset paths")
        return self.request(path, stream=True)


_gateway: Optional[CctvGateway] = None
_gateway_lock = threading.Lock()


def get_cctv_gateway() -> CctvGateway:
    global _gateway
    password = os.getenv("CCTV_PASSWORD", "")
    base_url = os.getenv("CCTV_BASE_URL", CCTV_BASE).rstrip("/")
    login_path = os.getenv("CCTV_LOGIN_PATH", LOGIN_PATH)
    catalogue_path = os.getenv("CCTV_CATALOGUE_PATH", CATALOGUE_PATH)
    if (_gateway is None or _gateway.password != password or _gateway.base_url != base_url
            or _gateway.login_path != login_path or _gateway.catalogue_path != catalogue_path):
        with _gateway_lock:
            if (_gateway is None or _gateway.password != password or _gateway.base_url != base_url
                    or _gateway.login_path != login_path or _gateway.catalogue_path != catalogue_path):
                _gateway = CctvGateway(password=password, base_url=base_url)
    return _gateway
