"""Public student registration, using the existing account transaction and hash."""
import re
import sqlite3
import threading
import time
from collections import OrderedDict

from fastapi import HTTPException, Request


def mount_registration(app, store):
    attempts = OrderedDict()
    attempts_lock = threading.Lock()

    @app.post('/api/auth/register', status_code=201)
    def register(payload: dict, request: Request):
        # Limit hash work as well as successful account creation. Memory stays bounded.
        ip = request.client.host if request.client else 'local'
        now = time.monotonic()
        with attempts_lock:
            recent = [t for t in attempts.pop(ip, []) if now - t < 60]
            if len(recent) >= 5:
                attempts[ip] = recent
                raise HTTPException(429, '注册尝试过多，请一分钟后再试。')
            attempts[ip] = recent + [now]
            while len(attempts) > 1024:
                attempts.popitem(last=False)

        username = payload.get('username')
        password = payload.get('password')
        confirmation = payload.get('confirm_password')
        if not isinstance(username, str):
            raise HTTPException(422, '账号格式不正确。')
        username = username.strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{3,30}', username):
            raise HTTPException(422, '账号需为 3–30 位英文字母、数字、底线或连字号。')
        if not isinstance(password, str) or not 10 <= len(password) <= 200 or password.isspace():
            raise HTTPException(422, '密码需为 10–200 个字符，不能全为空白。')
        if not isinstance(confirmation, str) or confirmation != password:
            raise HTTPException(422, '两次输入的密码不一致。')
        if store.find_user(username):
            raise HTTPException(409, '这个账号已被使用，请换一个账号，或返回登录。')
        try:
            # Never accept a client-provided role or demo flag.
            store.create_user(username, password, role='student', is_demo=False)
        except sqlite3.IntegrityError as error:
            # The unique constraint also covers simultaneous same-name requests.
            if 'UNIQUE constraint failed: users.username' not in str(error):
                raise
            raise HTTPException(409, '这个账号已被使用，请换一个账号，或返回登录。') from None
        except sqlite3.OperationalError:
            raise HTTPException(503, '注册服务暂时无法完成，请稍后重试。') from None
        # No session is created; the student must return to the login page.
        return {'username': username, 'message': '注册成功，请输入密码登录。'}
