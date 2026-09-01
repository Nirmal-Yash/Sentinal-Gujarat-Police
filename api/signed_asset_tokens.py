"""Short-lived signed tokens for browser media assets.

Asset tokens are deliberately separate from the Sentinel session JWT so media
URLs can be used by <img>/<video>/<HLS XHR> requests without exposing service
credentials. Tokens are scoped to one asset type and one resource identifier.
"""
from __future__ import annotations

import os
import time
from typing import Any

import jwt


_PLACEHOLDERS = {
    "", "change-me", "changeme", "sentinel-change-in-production",
    "replace-me", "replace-with-long-random-secret",
}


def _secret(env_name: str) -> str:
    value = (os.getenv(env_name, "") or "").strip()
    if not value or value.lower() in _PLACEHOLDERS:
        raise RuntimeError(f"{env_name} is not configured")
    return value


def issue_asset_token(*, kind: str, resource: str, env_name: str, ttl_seconds: int = 120) -> str:
    now = int(time.time())
    claims = {
        "sub": f"sentinel-{kind}",
        "asset": resource,
        "iat": now,
        "exp": now + max(30, min(int(ttl_seconds), 900)),
    }
    return jwt.encode(claims, _secret(env_name), algorithm="HS256")


def verify_asset_token(*, token: str, kind: str, resource: str, env_name: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(token, _secret(env_name), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid or expired asset token") from exc
    if claims.get("sub") != f"sentinel-{kind}" or str(claims.get("asset", "")) != str(resource):
        raise ValueError("Asset token is not valid for this resource")
    return claims
