import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth import AUTH_REQUIRED, COOKIE_MAX_AGE, COOKIE_NAME, COOKIE_SAMESITE, COOKIE_SECURE, REFRESH_COOKIE_NAME, REFRESH_TOKEN_HOURS, Principal, current_principal, require_role, verify_password, issue_access_token, issue_refresh_token, hash_password, enforce_session_limit, is_locked, record_attempt
from rate_limit import rate_limit
from security_hardening import enforce_password_policy

router = APIRouter(prefix='/auth', tags=['auth'])

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)

class UserCreate(Login):
    role: str = 'VIEWER'


def set_auth_cookies(response: Response, access_token: str, access_expires, refresh_token: str | None = None, refresh_expires=None):
    access_max = max(300, int((access_expires - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(COOKIE_NAME, access_token, max_age=min(access_max, COOKIE_MAX_AGE), httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, path='/')
    if refresh_token and refresh_expires:
        refresh_max = max(300, int((refresh_expires - datetime.now(timezone.utc)).total_seconds()))
        response.set_cookie(REFRESH_COOKIE_NAME, refresh_token, max_age=min(refresh_max, REFRESH_TOKEN_HOURS * 3600), httponly=True, secure=COOKIE_SECURE, samesite='strict', path='/api/auth/refresh')


@router.get('/config')
async def config(db: AsyncSession = Depends(get_db)):
    admin_exists = bool(await db.scalar(text("SELECT 1 FROM users WHERE role IN ('ADMIN','SUPERADMIN') AND is_active=TRUE LIMIT 1")))
    bootstrap_configured = bool(os.getenv('BOOTSTRAP_ADMIN_USERNAME','').strip() and os.getenv('BOOTSTRAP_ADMIN_PASSWORD',''))
    return {'auth_required': AUTH_REQUIRED, 'test_enabled': os.getenv('TEST_ENDPOINT_ENABLED','true').lower() == 'true', 'session_persistent': True, 'access_token_minutes': int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES','15')), 'refresh_token_hours': REFRESH_TOKEN_HOURS, 'bootstrap_admin_configured': bootstrap_configured, 'admin_available': admin_exists, 'login_available': (not AUTH_REQUIRED) or admin_exists}

@router.post('/login', dependencies=[Depends(rate_limit('auth-login', 5, 60))])
async def login(body: Login, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if await is_locked(body.username.strip(), request, db):
        await record_attempt(body.username, request, False, db); await db.commit()
        raise HTTPException(423, 'Account temporarily locked due to repeated failed attempts')
    row = (await db.execute(text("SELECT id, username, password_hash, role FROM users WHERE username=:username AND is_active=TRUE"), {'username': body.username.strip()})).mappings().first()
    if not row or not verify_password(body.password, row['password_hash']):
        await record_attempt(body.username, request, False, db); await db.commit()
        raise HTTPException(401, 'Invalid username or password')
    await record_attempt(body.username, request, True, db)
    await enforce_session_limit(str(row['id']), db)
    session = (await db.execute(text("INSERT INTO user_sessions(user_id,jti,expires_at) VALUES(CAST(:uid AS uuid),CAST(:jti AS uuid),:expires) RETURNING id"), {'uid': str(row['id']), 'jti': str(__import__('uuid').uuid4()), 'expires': datetime.now(timezone.utc)})).mappings().one()
    access, access_jti, access_expires = issue_access_token(str(row['id']), row['username'], row['role'], str(session['id']))
    await db.execute(text("UPDATE user_sessions SET jti=CAST(:jti AS uuid),expires_at=:expires WHERE id=CAST(:sid AS uuid)"), {'sid': str(session['id']), 'jti': access_jti, 'expires': access_expires})
    refresh, refresh_jti, refresh_expires = issue_refresh_token(str(row['id']), str(session['id']))
    await db.commit()
    set_auth_cookies(response, access, access_expires, refresh, refresh_expires)
    return {'access_token': access, 'token_type': 'bearer', 'expires_at': access_expires, 'user': {'id': str(row['id']), 'username': row['username'], 'role': row['role']}, 'refresh_expires_at': refresh_expires}

@router.post('/refresh', dependencies=[Depends(rate_limit('auth-refresh', 30, 60))])
async def refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME), db: AsyncSession = Depends(get_db)):
    if not AUTH_REQUIRED:
        return {'access_token': None, 'token_type': 'bearer', 'expires_at': None}
    if not refresh_token:
        raise HTTPException(401, 'Refresh token required')
    try:
        import jwt
        from auth import REFRESH_SECRET, ALGORITHM
        claims = jwt.decode(refresh_token, REFRESH_SECRET, algorithms=[ALGORITHM])
        if claims.get('type') != 'refresh': raise ValueError('wrong token type')
        jti = claims['jti']; sid = claims['sid']; uid = claims['sub']
    except Exception as exc:
        raise HTTPException(401, 'Invalid or expired refresh token') from exc
    revoked = await db.scalar(text('SELECT 1 FROM revoked_tokens WHERE jti=CAST(:jti AS uuid) AND expires_at>NOW()'), {'jti': jti})
    if revoked:
        await db.execute(text('UPDATE user_sessions SET revoked=TRUE WHERE user_id=CAST(:uid AS uuid)'), {'uid': uid}); await db.commit()
        raise HTTPException(401, 'Refresh token reuse detected')
    row = (await db.execute(text("SELECT u.username,u.role,s.revoked FROM users u JOIN user_sessions s ON s.user_id=u.id WHERE u.id=CAST(:uid AS uuid) AND s.id=CAST(:sid AS uuid) AND u.is_active=TRUE"), {'uid': uid, 'sid': sid})).mappings().first()
    if not row or row['revoked']:
        raise HTTPException(401, 'Session is no longer valid')
    await db.execute(text('INSERT INTO revoked_tokens(jti,expires_at) VALUES(CAST(:jti AS uuid),to_timestamp(:exp)) ON CONFLICT (jti) DO NOTHING'), {'jti': jti, 'exp': claims['exp']})
    access, access_jti, access_expires = issue_access_token(uid, row['username'], row['role'], sid)
    await db.execute(text('UPDATE user_sessions SET jti=CAST(:jti AS uuid),expires_at=:expires WHERE id=CAST(:sid AS uuid)'), {'sid': sid, 'jti': access_jti, 'expires': access_expires})
    new_refresh, _, refresh_expires = issue_refresh_token(uid, sid)
    await db.commit()
    set_auth_cookies(response, access, access_expires, new_refresh, refresh_expires)
    return {'access_token': access, 'token_type': 'bearer', 'expires_at': access_expires, 'refresh_expires_at': refresh_expires, 'user': {'id': uid, 'username': row['username'], 'role': row['role']}}

@router.post('/logout')
async def logout(response: Response, principal: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    if principal.jti:
        await db.execute(text('UPDATE user_sessions SET revoked=TRUE WHERE jti=CAST(:jti AS uuid)'), {'jti': principal.jti}); await db.commit()
    response.delete_cookie(COOKIE_NAME, path='/'); response.delete_cookie(REFRESH_COOKIE_NAME, path='/api/auth/refresh')
    return {'status': 'logged_out'}

@router.get('/me')
async def me(principal: Principal = Depends(current_principal)):
    return {'id': principal.user_id, 'username': principal.username, 'role': principal.role}

@router.post('/users', status_code=201)
async def create_user(body: UserCreate, principal: Principal = Depends(require_role('SUPERADMIN')), db: AsyncSession = Depends(get_db)):
    role = body.role.upper()
    if role not in {'SUPERADMIN','ADMIN','OPERATOR','INVESTIGATOR','AUDITOR','VIEWER'}: raise HTTPException(422, 'Invalid role')
    enforce_password_policy(body.password, body.username)
    try:
        row = (await db.execute(text('INSERT INTO users(username,password_hash,role) VALUES(:username,:hash,:role) RETURNING id,username,role,created_at'), {'username': body.username.strip(), 'hash': hash_password(body.password), 'role': role})).mappings().one(); await db.commit(); return dict(row)
    except Exception as exc:
        await db.rollback(); raise HTTPException(409, 'Username already exists') from exc
