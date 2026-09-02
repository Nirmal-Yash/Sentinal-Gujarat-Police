from __future__ import annotations
import os
import jwt
from fastapi import Request
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

EVENTS = {
    "/auth/login": ("AUTH_LOGIN", "MEDIUM"),
    "/auth/refresh": ("AUTH_REFRESH", "LOW"),
    "/auth/logout": ("AUTH_LOGOUT", "LOW"),
    "/search/plate": ("INVESTIGATION_PLATE", "MEDIUM"),
    "/search/person/": ("INVESTIGATION_PERSON", "HIGH"),
    "/evidence/": ("EVIDENCE_ACCESS", "MEDIUM"),
    "/watchlist/": ("WATCHLIST_ACCESS", "HIGH"),
    "/camera-imports/": ("CAMERA_REGISTRY", "MEDIUM"),
    "/cameras/onboard": ("CAMERA_REGISTRY", "MEDIUM"),
}


def actor_from_request(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return "cookie-session" if request.cookies.get("sentinel_session") else "anonymous"
    try:
        claims = jwt.decode(header[7:], os.getenv("SECRET_KEY", ""), algorithms=["HS256"], options={"verify_exp": False})
        return str(claims.get("username") or claims.get("sub") or "authenticated")[:255]
    except Exception:
        return "authenticated"


class SecurityAuditMiddleware(BaseHTTPMiddleware):
    """Persist security-relevant request outcomes without blocking the request."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        match = next((key for key in EVENTS if request.url.path.startswith(key)), None)
        if match:
            try:
                event_type, severity = EVENTS[match]
                from database import Session
                async with Session() as db:
                    await db.execute(
                        text("""INSERT INTO security_audit_events
                        (event_type,severity,actor,message,ip_address,user_agent,request_id,payload_json)
                        VALUES(:event,:severity,:actor,:message,:ip,:ua,:request_id,'{}'::jsonb)"""),
                        {
                            "event": event_type if response.status_code < 400 else event_type + "_FAILED",
                            "severity": severity,
                            "actor": actor_from_request(request),
                            "message": f"{request.method} {request.url.path} -> {response.status_code}",
                            "ip": request.client.host if request.client else None,
                            "ua": request.headers.get("user-agent", "")[:255],
                            "request_id": response.headers.get("X-Request-Id"),
                        },
                    )
                    await db.commit()
            except Exception:
                pass
        return response
