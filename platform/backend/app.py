import asyncio
import hmac
import logging
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .config import Settings
from .db import Database
from .formats import ASPECT_SIZES, SIZE_ASPECTS, job_dimensions
from .security import bootstrap_admin, check_password, create_user, hash_password, now, token_hash

COOKIE = 'moss_session'


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class JobInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt: str = Field(min_length=1, max_length=4000)
    negative_prompt: str = Field(default='', max_length=4000)
    steps: StrictInt = 16
    seed: StrictInt = Field(default=42, ge=0, le=4294967295)
    aspect_ratio: Literal['1:1', '16:9', '9:16'] = '1:1'

    @field_validator('prompt')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('提示词不能为空')
        return value.strip()

    @field_validator('steps')
    @classmethod
    def allowed_steps(cls, value):
        if value not in (8, 16, 20):
            raise ValueError('步数须为8、16或20')
        return value


class UserInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=10, max_length=128)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


def create_app(settings=None):
    settings = settings or Settings()
    db = Database(settings.db_path)
    if settings.bootstrap_default_admin:
        bootstrap_admin(db)
    stop = threading.Event()
    limiter_lock = threading.Lock()
    attempts = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app):
        thread = None
        lock_file = None
        if settings.worker_enabled:
            # One process per SQLite worker. A second instance must fail closed.
            lock_file = open(settings.data_dir / 'worker.lock', 'a+b')
            try:
                if __import__('os').name == 'nt':
                    import msvcrt
                    lock_file.seek(0)
                    if not lock_file.read(1):
                        lock_file.write(b'0')
                        lock_file.flush()
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                lock_file.close()
                raise RuntimeError('已有平台worker运行，请勿多开后端')
            from .worker import run_worker
            stop.clear()
            thread = threading.Thread(target=run_worker, args=(db, settings, stop), daemon=True, name='moss-worker')
            app.state.worker_thread = thread
            thread.start()
        try:
            yield
        finally:
            stop.set()
            if thread:
                # Keep the singleton lock until targeted GPU cancellation is confirmed.
                await asyncio.to_thread(thread.join)
            if lock_file:
                lock_file.close()

    app = FastAPI(title='MOSS Studio', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db
    app.state.settings = settings
    app.state.worker_thread = None

    @app.middleware('http')
    async def trust_boundary(request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if (origin and origin not in settings.allowed_origins) or request.headers.get('sec-fetch-site') == 'cross-site':
                return __import__('starlette.responses', fromlist=['JSONResponse']).JSONResponse({'detail': '请求来源不受信任'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    def current(request: Request):
        token = request.cookies.get(COOKIE, '')
        if not token or len(token) > 128:
            raise HTTPException(401, '请先登录')
        session = db.one('SELECT s.csrf_token,s.token_hash,u.id,u.username,u.role,u.is_active,u.must_change_password FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?', (token_hash(token), time.time()))
        if not session or not session['is_active']:
            raise HTTPException(401, '登录已失效，请重新登录')
        if session['must_change_password'] and request.url.path not in ('/api/auth/session','/api/auth/logout','/api/auth/change-password'):
            raise HTTPException(403, '首次登录必须先修改密码')
        return session

    def write_user(request: Request, user=Depends(current)):
        csrf = request.headers.get('X-CSRF-Token', '')
        if not hmac.compare_digest(csrf, user['csrf_token']):
            raise HTTPException(403, '安全校验失败，请刷新页面后重试')
        return user

    def admin(user=Depends(current)):
        if user['role'] != 'admin':
            raise HTTPException(403, '需要管理员权限')
        return user

    def write_admin(user=Depends(write_user)):
        if user['role'] != 'admin':
            raise HTTPException(403, '需要管理员权限')
        return user

    def public_user(user):
        return {**{k: user[k] for k in ('id', 'username', 'role')},
                'must_change_password': bool(user.get('must_change_password', False))}

    def owned(jid, user):
        job = db.one('SELECT * FROM jobs WHERE id=? AND owner_id=?', (jid, user['id']))
        if not job:
            raise HTTPException(404, '记录不存在')
        return job

    def public_job(job):
        fields = ('id', 'prompt', 'negative_prompt', 'steps', 'seed', 'status', 'created_at', 'started_at', 'finished_at', 'error', 'elapsed_seconds')
        result = {k: job.get(k) for k in fields}
        queued = db.all("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at,rowid") if job['status'] == 'queued' else []
        ids = [row['id'] for row in queued]
        width, height = job_dimensions(job)
        result.update(width=width, height=height, aspect_ratio=SIZE_ASPECTS[(width,height)], image_url=f'/api/jobs/{job["id"]}/image' if job['status'] == 'succeeded' else None,
                      queue_position=ids.index(job['id']) + 1 if job['id'] in ids else None)
        return result

    @app.get('/api/auth/bootstrap')
    def bootstrap_status():
        pending = db.one("SELECT id FROM users WHERE username='admin' AND role='admin' AND is_active=1 AND must_change_password=1")
        return {'initial_setup_required': bool(pending)}

    @app.post('/api/auth/login')
    def login(body: Login, request: Request, response: Response):
        key = request.client.host if request.client else 'local'
        with limiter_lock:
            bucket = attempts[key]
            while bucket and bucket[0] < time.time() - 600:
                bucket.popleft()
            if len(bucket) >= 20:
                raise HTTPException(429, '登录尝试过多，请10分钟后再试')
            bucket.append(time.time())
        user = db.one('SELECT * FROM users WHERE username=?', (body.username,))
        # Do a comparable hash operation for nonexistent users to reduce enumeration.
        encoded = user['password_hash'] if user else hash_password('NonexistentUserDummyPassword')
        valid = check_password(body.password, encoded)
        if not user or not valid or not user['is_active']:
            raise HTTPException(401, '账号或密码错误')
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with db.transaction() as c:
            # Recheck active/password state inside the insert transaction (disable/login race).
            active = c.execute('SELECT is_active,password_hash FROM users WHERE id=?', (user['id'],)).fetchone()
            if not active['is_active'] or active['password_hash'] != user['password_hash']:
                raise HTTPException(401, '账号或密码错误')
            old_token = request.cookies.get(COOKIE)
            if old_token:
                c.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(old_token),))
            c.execute('DELETE FROM sessions WHERE expires_at<=?', (time.time(),))
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token_hash(token), user['id'], csrf, time.time() + settings.session_seconds))
        response.set_cookie(COOKIE, token, httponly=True, secure=settings.secure_cookie, samesite='strict', max_age=settings.session_seconds, path='/')
        return {'user': public_user(user), 'csrf_token': csrf}

    @app.get('/api/auth/session')
    def session(user=Depends(current)):
        return {'user': public_user(user), 'csrf_token': user['csrf_token']}

    @app.post('/api/auth/logout')
    def logout(response: Response, user=Depends(write_user)):
        db.execute('DELETE FROM sessions WHERE token_hash=?', (user['token_hash'],))
        response.delete_cookie(COOKIE, path='/')
        return {'ok': True}

    @app.post('/api/auth/change-password')
    def change_password(body: PasswordChange, response: Response, user=Depends(write_user)):
        if body.current_password == body.new_password:
            raise HTTPException(400,'新密码不能与当前密码相同')
        encoded = hash_password(body.new_password)
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with db.transaction() as c:
            row = c.execute('SELECT password_hash,is_active FROM users WHERE id=?',(user['id'],)).fetchone()
            valid_session = c.execute('SELECT 1 FROM sessions WHERE token_hash=? AND expires_at>?',(user['token_hash'],time.time())).fetchone()
            if not row or not row['is_active'] or not valid_session:
                raise HTTPException(401,'登录已失效，请重新登录')
            if not check_password(body.current_password,row['password_hash']):
                raise HTTPException(400,'当前密码不正确')
            c.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',(encoded,user['id']))
            c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token_hash(token),user['id'],csrf,time.time()+settings.session_seconds))
        response.set_cookie(COOKIE,token,httponly=True,secure=settings.secure_cookie,samesite='strict',max_age=settings.session_seconds,path='/')
        updated = db.one('SELECT * FROM users WHERE id=?',(user['id'],))
        return {'user':public_user(updated),'csrf_token':csrf}

    @app.get('/api/status')
    def status(user=Depends(current)):
        from .engine import ComfyEngine
        return {'engine_online': ComfyEngine(settings).online(), 'queue_length': db.one("SELECT count(*) AS n FROM jobs WHERE status='queued'")['n'],
                'running': bool(db.one("SELECT id FROM jobs WHERE status='running'")), 'model': 'MOSS-Image INT8', 'max_concurrency': 1,
                'worker_online': bool(app.state.worker_thread and app.state.worker_thread.is_alive())}

    @app.get('/api/jobs')
    def jobs(page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=50)] = 12,
             status: Literal['queued','running','succeeded','failed','cancelled'] | None = None, user=Depends(current)):
        where, params = 'owner_id=?', [user['id']]
        if status:
            where += ' AND status=?'
            params.append(status)
        total = db.one('SELECT count(*) AS n FROM jobs WHERE ' + where, params)['n']
        rows = db.all('SELECT * FROM jobs WHERE ' + where + ' ORDER BY created_at DESC,rowid DESC LIMIT ? OFFSET ?', params + [page_size, (page-1)*page_size])
        return {'items': [public_job(j) for j in rows], 'total': total, 'page': page, 'page_size': page_size}

    @app.post('/api/jobs', status_code=201)
    def new_job(body: JobInput, user=Depends(write_user)):
        jid = secrets.token_hex(16)
        width, height = ASPECT_SIZES[body.aspect_ratio]
        with db.transaction() as c:
            if c.execute("SELECT 1 FROM jobs WHERE owner_id=? AND status IN ('queued','running')", (user['id'],)).fetchone():
                raise HTTPException(409, '你已有排队或生成中的任务，请等待完成')
            if c.execute("SELECT count(*) FROM jobs WHERE status='queued'").fetchone()[0] >= 20:
                raise HTTPException(429, '等待队列已满，请稍后再试')
            c.execute('INSERT INTO jobs(id,owner_id,prompt,negative_prompt,steps,seed,status,created_at,width,height) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (jid,user['id'],body.prompt,body.negative_prompt,body.steps,body.seed,'queued',now(),width,height))
        return public_job(owned(jid,user))

    @app.get('/api/jobs/{jid}')
    def job(jid: str, user=Depends(current)):
        return public_job(owned(jid,user))

    @app.post('/api/jobs/{jid}/cancel')
    def cancel(jid: str, user=Depends(write_user)):
        owned(jid,user)
        if not db.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE id=? AND status='queued'", (now(),jid)):
            raise HTTPException(409, '只能取消尚未开始的任务')
        return public_job(owned(jid,user))

    def image_path(job):
        if job['status'] != 'succeeded' or not job['image_path']:
            raise HTTPException(404, '图片不存在')
        path = Path(job['image_path'])
        if not path.is_absolute():
            path = settings.data_dir / path
        path = path.resolve()
        if not path.is_relative_to((settings.data_dir / 'images').resolve()) or not path.is_file():
            raise HTTPException(404, '图片不存在')
        return path

    @app.get('/api/jobs/{jid}/image')
    def image(jid: str, download: bool=False, user=Depends(current)):
        path = image_path(owned(jid,user))
        return FileResponse(path, media_type='image/png', filename=f'moss-{jid}.png' if download else None)

    @app.delete('/api/jobs/{jid}')
    def delete(jid: str, user=Depends(write_user)):
        j = owned(jid,user)
        if j['status'] in ('queued','running'):
            raise HTTPException(409, '请先取消排队任务；运行中任务无法删除')
        if j['image_path']:
            try:
                image_path(j).unlink()
            except HTTPException:
                pass
            except OSError:
                raise HTTPException(409, '图片暂时无法删除，请稍后重试')
        db.execute('DELETE FROM jobs WHERE id=? AND owner_id=?', (jid,user['id']))
        return {'ok':True}

    def public_admin_user(u):
        return {**public_user(u), 'is_active':bool(u['is_active']), 'created_at':u['created_at']}

    @app.get('/api/admin/users')
    def users(user=Depends(admin)):
        return {'items':[public_admin_user(u) for u in db.all('SELECT * FROM users ORDER BY created_at')]}

    @app.post('/api/admin/users',status_code=201)
    def new_user(body: UserInput, user=Depends(write_admin)):
        try:
            uid = create_user(db,body.username,body.password)
        except ValueError as exc:
            raise HTTPException(422,str(exc))
        except sqlite3.IntegrityError:
            raise HTTPException(409,'账号已存在')
        return public_admin_user(db.one('SELECT * FROM users WHERE id=?',(uid,)))

    @app.patch('/api/admin/users/{uid}')
    def update_user(uid: str, body: UserUpdate, user=Depends(write_admin)):
        if not db.one('SELECT id FROM users WHERE id=?',(uid,)):
            raise HTTPException(404,'用户不存在')
        if uid == user['id'] and body.is_active is False:
            raise HTTPException(409,'不能停用当前管理员账号')
        encoded = hash_password(body.password) if body.password else None
        with db.transaction() as c:
            if body.is_active is not None:
                c.execute('UPDATE users SET is_active=? WHERE id=?',(int(body.is_active),uid))
                if body.is_active is False:
                    c.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE owner_id=? AND status='queued'",(now(),uid))
            if encoded:
                c.execute('UPDATE users SET password_hash=? WHERE id=?',(encoded,uid))
            if encoded or body.is_active is False:
                c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        return public_admin_user(db.one('SELECT * FROM users WHERE id=?',(uid,)))

    return app
