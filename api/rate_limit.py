"""Small Redis-backed rate limiter for sensitive API operations."""
import hashlib
import os
from fastapi import HTTPException, Request, status
import redis.asyncio as redis

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
CLIENT = redis.from_url(REDIS_URL, decode_responses=True)

def rate_limit(scope: str, limit: int, window_seconds: int):
    async def dependency(request: Request):
        forwarded = request.headers.get('x-forwarded-for', '')
        host = (forwarded.split(',')[0].strip() if forwarded else (request.client.host if request.client else 'unknown'))
        # Hash the address so Redis never stores raw client identifiers.
        client_key = hashlib.sha256(host.encode()).hexdigest()[:24]
        key = f'rate:{scope}:{client_key}'
        try:
            count = await CLIENT.incr(key)
            if count == 1:
                await CLIENT.expire(key, window_seconds)
            if count > limit:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail='Rate limit exceeded')
        except HTTPException:
            raise
        except Exception:
            # Security controls must not take the API offline when Redis is temporarily unavailable.
            return None
        return None
    return dependency
