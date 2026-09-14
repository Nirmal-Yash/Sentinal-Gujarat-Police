"""Authenticated gateway client for the current cctv.corp8.cloud infrastructure.

The CCTV provider requires an assigned email plus password. Credentials remain server-side for catalogue and HLS proxy requests.
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
    def __init__(self, email: str, password: str, base_url: str = CCTV_BASE, timeout: float = 15.0):
        self.email = (email or "").strip()
        self.password = password or ""
        self.base_url = base_url.rstrip("/")
        self.login_path = os.getenv("CCTV_LOGIN_PATH", LOGIN_PATH)
        self.catalogue_path = os.getenv("CCTV_CATALOGUE_PATH", CATALOGUE_PATH)
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.base_url}/",
            "Origin": self.base_url,
        })
        self._lock = threading.RLock()
        self._authenticated_at = 0.0
        self._last_login_error: Optional[str] = None
        self._key_cache: dict[str, tuple[float, bytes]] = {}
        self._segment_cache: dict[str, tuple[float, bytes, str]] = {}
        self._segment_cache_ttl = float(os.getenv("CCTV_SEGMENT_CACHE_TTL", "8"))

    @property
    def configured(self) -> bool:
        return bool(self.email and self.password)

    def _login_locked(self) -> None:
        if not self.email:
            raise RuntimeError("CCTV_EMAIL is not configured")
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
            data={"email": self.email, "password": self.password},
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
            if not (self._session.cookies.get_dict() or token):
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
            if response.status_code in {401, 403, 302, 303}:
                response.close()
                self._login_locked()
                response = self._session.get(
                    f"{self.base_url}{path}",
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=stream,
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
            number = int(suffix)
            if number < 1 or number > 30:
                raise ValueError("camera id must be cam01 through cam30")
            suffix = str(number).zfill(2)
        elif not __import__("re").fullmatch(r"cam(0[1-9]|[12][0-9]|30)", "cam"+suffix, __import__("re").IGNORECASE):
            raise ValueError("camera id must be cam01 through cam30")
        return f"/cam{suffix}/index.m3u8"

    def proxy_asset(self, asset_path: str) -> requests.Response:
        path = "/" + asset_path.lstrip("/")
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc:
            raise ValueError("Absolute URLs are not allowed in CCTV proxy asset paths")
        return self.request(path, stream=True)

    def get_cached_key(self, key_path: str = "/enc.key") -> bytes:
        now = time.monotonic()
        with self._lock:
            cached = self._key_cache.get(key_path)
            if cached and (now - cached[0]) < 600:
                return cached[1]
        resp = self.request(key_path)
        try:
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch encryption key: HTTP {resp.status_code}")
            key_bytes = resp.content
            with self._lock:
                self._key_cache[key_path] = (now, key_bytes)
            return key_bytes
        finally:
            resp.close()

    def get_cached_segment(self, asset_path: str) -> tuple[bytes, str] | None:
        now = time.monotonic()
        with self._lock:
            cached = self._segment_cache.get(asset_path)
            if cached and (now - cached[0]) < self._segment_cache_ttl:
                return cached[1], cached[2]
        return None

    def store_cached_segment(self, asset_path: str, body: bytes, content_type: str) -> None:
        with self._lock:
            self._segment_cache[asset_path] = (time.monotonic(), body, content_type)
            if len(self._segment_cache) > 256:
                oldest = sorted(self._segment_cache.items(), key=lambda item: item[1][0])[:64]
                for key, _ in oldest:
                    self._segment_cache.pop(key, None)


_gateway: Optional[CctvGateway] = None
_gateway_lock = threading.Lock()


def get_cctv_gateway() -> CctvGateway:
    global _gateway
    email = os.getenv("CCTV_EMAIL", "").strip()
    password = os.getenv("CCTV_PASSWORD", "")
    base_url = os.getenv("CCTV_BASE_URL", CCTV_BASE).rstrip("/")
    login_path = os.getenv("CCTV_LOGIN_PATH", LOGIN_PATH)
    catalogue_path = os.getenv("CCTV_CATALOGUE_PATH", CATALOGUE_PATH)
    if (_gateway is None or _gateway.email != email or _gateway.password != password or _gateway.base_url != base_url
            or _gateway.login_path != login_path or _gateway.catalogue_path != catalogue_path):
        with _gateway_lock:
            if (_gateway is None or _gateway.password != password or _gateway.base_url != base_url
                    or _gateway.login_path != login_path or _gateway.catalogue_path != catalogue_path):
                _gateway = CctvGateway(email=email, password=password, base_url=base_url)
    return _gateway
