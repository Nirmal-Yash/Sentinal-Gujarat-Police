import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from auth import AUTH_REQUIRED, COOKIE_MAX_AGE, COOKIE_NAME, COOKIE_SAMESITE, COOKIE_SECURE, Principal, current_principal, require_role, verify_password, issue_token, hash_password
from rate_limit import rate_limit

router = APIRouter(prefix='/auth', tags=['auth'])

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)

class UserCreate(Login):
    role: str = 'VIEWER'


def set_session_cookie(response: Response, token: str, expires_at):
    max_age = max(300, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(COOKIE_NAME, token, max_age=min(max_age, COOKIE_MAX_AGE), httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, path='/')


@router.get('/config')
async def config(db: AsyncSession = Depends(get_db)):
    admin_exists = bool(await db.scalar(text("SELECT 1 FROM users WHERE role IN ('ADMIN','SUPERADMIN') AND is_active=TRUE LIMIT 1")))
    bootstrap_configured = bool(os.getenv('BOOTSTRAP_ADMIN_USERNAME','').strip() and os.getenv('BOOTSTRAP_ADMIN_PASSWORD',''))
    return {'auth_required': AUTH_REQUIRED, 'test_enabled': os.getenv('TEST_ENDPOINT_ENABLED','true').lower() == 'true', 'session_persistent': True, 'bootstrap_admin_configured': bootstrap_configured, 'admin_available': admin_exists, 'login_available': (not AUTH_REQUIRED) or admin_exists}

@router.post('/login', dependencies=[Depends(rate_limit('auth-login', int(os.getenv('AUTH_LOGIN_RATE_LIMIT','10')), int(os.getenv('AUTH_LOGIN_RATE_WINDOW','60'))))])
async def login(body: Login, response: Response, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(text("SELECT id, username, password_hash, role FROM users WHERE username=:username AND is_active=TRUE"), {'username': body.username})).mappings().first()
    if not row or not verify_password(body.password, row['password_hash']):
        raise HTTPException(401, 'Invalid username or password')
    token, jti, expires = issue_token(str(row['id']), row['username'], row['role'])
    await db.execute(text('INSERT INTO user_sessions(user_id,jti,expires_at) VALUES(CAST(:uid AS uuid),CAST(:jti AS uuid),:expires)'), {'uid': str(row['id']), 'jti': jti, 'expires': expires})
    await db.execute(text('UPDATE users SET last_login=NOW() WHERE id=CAST(:uid AS uuid)'), {'uid': str(row['id'])})
    await db.commit()
    set_session_cookie(response, token, expires)
    return {'access_token': token, 'token_type': 'bearer', 'expires_at': expires, 'user': {'id': str(row['id']), 'username': row['username'], 'role': row['role']}}

@router.post('/refresh')
async def refresh(response: Response, principal: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    if not AUTH_REQUIRED:
        return {'access_token': None, 'token_type': 'bearer', 'expires_at': None, 'user': {'id': principal.user_id, 'username': principal.username, 'role': principal.role}}
    if not principal.user_id or not principal.jti:
        raise HTTPException(401, 'Refresh requires an authenticated session')
    row = (await db.execute(text('SELECT username, role FROM users WHERE id=CAST(:uid AS uuid) AND is_active=TRUE'), {'uid': principal.user_id})).mappings().first()
    if not row: raise HTTPException(401, 'User session is no longer valid')
    token, new_jti, expires = issue_token(principal.user_id, row['username'], row['role'])
    await db.execute(text('UPDATE user_sessions SET revoked=TRUE WHERE jti=CAST(:jti AS uuid)'), {'jti': principal.jti})
    await db.execute(text('INSERT INTO user_sessions(user_id,jti,expires_at) VALUES(CAST(:uid AS uuid),CAST(:jti AS uuid),:expires)'), {'uid': principal.user_id, 'jti': new_jti, 'expires': expires})
    await db.commit()
    set_session_cookie(response, token, expires)
    return {'access_token': token, 'token_type': 'bearer', 'expires_at': expires, 'user': {'id': principal.user_id, 'username': row['username'], 'role': row['role']}}

@router.post('/logout')
async def logout(response: Response, principal: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    if principal.jti:
        await db.execute(text('UPDATE user_sessions SET revoked=TRUE WHERE jti=CAST(:jti AS uuid)'), {'jti': principal.jti}); await db.commit()
    response.delete_cookie(COOKIE_NAME, path='/')
    return {'status': 'logged_out'}

@router.get('/me')
async def me(principal: Principal = Depends(current_principal)):
    return {'id': principal.user_id, 'username': principal.username, 'role': principal.role}

@router.post('/users', status_code=201)
async def create_user(body: UserCreate, principal: Principal = Depends(require_role('SUPERADMIN')), db: AsyncSession = Depends(get_db)):
    role = body.role.upper()
    if role not in {'SUPERADMIN','ADMIN','OPERATOR','INVESTIGATOR','AUDITOR','VIEWER'}: raise HTTPException(422, 'Invalid role')
    try:
        row = (await db.execute(text('INSERT INTO users(username,password_hash,role) VALUES(:username,:hash,:role) RETURNING id,username,role,created_at'), {'username': body.username, 'hash': hash_password(body.password), 'role': role})).mappings().one(); await db.commit(); return dict(row)
    except Exception as exc:
        await db.rollback(); raise HTTPException(409, 'Username already exists') from exc
