"""Password accounts use phone-shaped identifiers; no SMS or phone ownership claim."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field


class Credentials(BaseModel):
    phone: str = Field(pattern=r'^1\d{10}$')
    password: str = Field(min_length=8, max_length=72)


def build_router(get_store, identify, local_secret):
    router = APIRouter(prefix='/api/v1/auth')
    attempts = {}
    lock = threading.Lock()

    def limit(request):
        ip = request.client.host if request.client else 'unknown'
        with lock:
            cutoff = time.time() - 900
            for address in list(attempts):
                attempts[address] = [t for t in attempts[address] if t > cutoff]
                if not attempts[address]:
                    del attempts[address]
            values = attempts.setdefault(ip, [])
            if len(values) >= 30:
                raise HTTPException(429, '尝试过于频繁，请稍后再试')
            values.append(time.time())

    def cloud(method, path, data=None, admin=False, token=None):
        store = get_store()
        key = store.key if admin else os.getenv('SUPABASE_PUBLISHABLE_KEY', '')
        headers = {'apikey': key}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        elif admin and not key.startswith('sb_'):
            headers['Authorization'] = 'Bearer ' + key
        try:
            return httpx.request(method, store.url + '/auth/v1' + path, headers=headers, json=data, timeout=30)
        except httpx.RequestError:
            raise HTTPException(503, '账号服务暂时无法连接，请稍后重试')

    def alias(phone):
        return 'p' + hashlib.sha256(phone.encode()).hexdigest() + '@accounts.gongmingbai.invalid'

    def password_hash(password, salt):
        return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 260000).hex()

    def local_session(owner, phone):
        expiry = str(int(time.time()) + 86400 * 30)
        message = owner + '.' + expiry + '.' + secrets.token_hex(12)
        return {'access_token': message + '.' + hmac.new(local_secret, message.encode(), 'sha256').hexdigest(),
                'user': {'id': owner, 'phone': phone, 'is_anonymous': False}, 'mode': 'local-development'}

    def user_info(owner, authorization):
        store = get_store()
        if store.cloud:
            r = cloud('GET', '/user', token=authorization.removeprefix('Bearer '))
            if r.status_code != 200:
                raise HTTPException(401, '请重新登录')
            u = r.json()
            return {'id': owner, 'phone': u.get('user_metadata', {}).get('account_phone'),
                    'is_anonymous': u.get('is_anonymous', False)}
        with store.db() as db:
            row = db.execute('SELECT phone FROM accounts WHERE owner_id=?', (owner,)).fetchone()
        return {'id': owner, 'phone': row[0] if row else None, 'is_anonymous': row is None}

    @router.post('/register')
    def register(body: Credentials, request: Request, authorization: str = Header(default='')):
        limit(request)
        store = get_store()
        owner = identify(authorization) if authorization else None
        if owner and not user_info(owner, authorization)['is_anonymous']:
            raise HTTPException(409, '当前已登录账号，请先退出再注册新账号')
        if store.cloud:
            data = {'email': alias(body.phone), 'password': body.password, 'email_confirm': True,
                    'user_metadata': {'account_phone': body.phone}}
            path = '/admin/users/' + owner if owner else '/admin/users'
            r = cloud('PUT' if owner else 'POST', path, data, admin=True)
            if r.status_code >= 400:
                code = r.json().get('error_code', '')
                if code in ('email_exists', 'email_address_not_authorized') or r.status_code == 422:
                    raise HTTPException(409, '该账号已注册，请直接登录')
                raise HTTPException(503, '注册失败，请检查账号服务配置')
            return login_result(body)
        salt = secrets.token_hex(16)
        try:
            with store.lock, store.db() as db:
                db.execute('INSERT INTO accounts(phone,owner_id,salt,password_hash) VALUES(?,?,?,?)',
                           (body.phone, owner or str(uuid.uuid4()), salt, password_hash(body.password, salt)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, '该账号已注册，请直接登录')
        return login_result(body)

    def login_result(body):
        store = get_store()
        if store.cloud:
            r = cloud('POST', '/token?grant_type=password', {'email': alias(body.phone), 'password': body.password})
            if r.status_code != 200:
                raise HTTPException(401, '手机号或密码不正确')
            result = r.json()
            result['user']['phone'] = body.phone
            return result
        with store.db() as db:
            row = db.execute('SELECT owner_id,salt,password_hash FROM accounts WHERE phone=?', (body.phone,)).fetchone()
        salt = row[1] if row else '00' * 16
        value = password_hash(body.password, salt)
        if not row or not hmac.compare_digest(row[2], value):
            raise HTTPException(401, '手机号或密码不正确')
        return local_session(row[0], body.phone)

    @router.post('/login')
    def login(body: Credentials, request: Request):
        limit(request)
        return login_result(body)

    @router.get('/me')
    def me(authorization: str = Header(default='')):
        return user_info(identify(authorization), authorization)

    @router.post('/logout')
    def logout(authorization: str = Header(default='')):
        identify(authorization)
        store = get_store()
        if store.cloud:
            r = cloud('POST', '/logout?scope=local', token=authorization.removeprefix('Bearer '))
            if r.status_code >= 400:
                raise HTTPException(503, '退出失败，请稍后重试')
        else:
            digest = hashlib.sha256(authorization.removeprefix('Bearer ').encode()).hexdigest()
            with store.db() as db:
                db.execute('INSERT OR IGNORE INTO revoked_tokens VALUES (?)', (digest,))
        return {'ok': True}

    return router
