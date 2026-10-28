import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Settings
from backend.db import Database
from backend.security import create_user


def test_bootstrap_forces_change_and_rotates_session(tmp_path):
    settings=Settings(data_dir=tmp_path,worker_enabled=False,bootstrap_default_admin=True)
    app=create_app(settings)
    with TestClient(app) as c:
        assert c.get('/api/auth/bootstrap').json()['initial_setup_required'] is True
        r=c.post('/api/auth/login',json={'username':'admin','password':'123456'})
        assert r.status_code==200
        assert r.json()['user']['must_change_password'] is True
        old_cookie=c.cookies.get('moss_session');old_csrf=r.json()['csrf_token'];h={'X-CSRF-Token':old_csrf}
        for path in ['/api/jobs','/api/status','/api/admin/users']:
            assert c.get(path).status_code==403
        assert c.post('/api/jobs',headers=h,json={'prompt':'red teapot','steps':8,'seed':42}).status_code==403
        assert c.post('/api/auth/change-password',headers={},json={'current_password':'123456','new_password':'NewStrongPass42!'}).status_code==403
        assert c.post('/api/auth/change-password',headers=h,json={'current_password':'wrong','new_password':'NewStrongPass42!'}).status_code==400
        assert c.post('/api/auth/change-password',headers=h,json={'current_password':'123456','new_password':'123456'}).status_code==422
        r=c.post('/api/auth/change-password',headers=h,json={'current_password':'123456','new_password':'NewStrongPass42!'})
        assert r.status_code==200,r.text
        assert r.json()['user']['must_change_password'] is False
        assert c.cookies.get('moss_session') != old_cookie
        assert r.json()['csrf_token'] != old_csrf
        assert c.get('/api/jobs').status_code==200
        assert c.get('/api/auth/bootstrap').json()['initial_setup_required'] is False
        with TestClient(app) as other:
            other.cookies.set('moss_session',old_cookie)
            assert other.get('/api/auth/session').status_code==401
        assert c.post('/api/auth/login',json={'username':'admin','password':'123456'}).status_code==401
        assert c.post('/api/auth/login',json={'username':'admin','password':'NewStrongPass42!'}).status_code==200
    # Never reset an existing administrator after restart.
    new_app=create_app(settings)
    with TestClient(new_app) as c:
        assert c.post('/api/auth/login',json={'username':'admin','password':'123456'}).status_code==401
        assert c.post('/api/auth/login',json={'username':'admin','password':'NewStrongPass42!'}).status_code==200


def test_bootstrap_never_overwrites_existing_users(tmp_path):
    s=Settings(data_dir=tmp_path,worker_enabled=False)
    d=Database(s.db_path);create_user(d,'customadmin','KeepExistingPass42!','admin')
    a=create_app(Settings(data_dir=tmp_path,worker_enabled=False,bootstrap_default_admin=True))
    with TestClient(a) as c:
        assert c.post('/api/auth/login',json={'username':'admin','password':'123456'}).status_code==401
        assert c.post('/api/auth/login',json={'username':'customadmin','password':'KeepExistingPass42!'}).status_code==200
