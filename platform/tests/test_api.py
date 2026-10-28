import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Settings
from backend.security import create_user

@pytest.fixture
def env(tmp_path):
    settings=Settings(data_dir=tmp_path,worker_enabled=False)
    app=create_app(settings)
    create_user(app.state.db,'admin','AdminTestPass42!','admin')
    create_user(app.state.db,'alice','AliceTestPass42!','user')
    create_user(app.state.db,'bravo','BravoTestPass42!','user')
    with TestClient(app) as client:
        yield app,client

def login(c,name='alice',password='AliceTestPass42!'):
    r=c.post('/api/auth/login',json={'username':name,'password':password})
    assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf_token']}

def submit(c,h,**kwargs):
    return c.post('/api/jobs',headers=h,json={'prompt':'A red ceramic teapot','steps':8,'seed':42,**kwargs})

def test_unauthorized(env):
    _,c=env
    assert c.get('/api/jobs').status_code==401
    assert c.get('/api/status').status_code==401
    assert c.get('/api/jobs/anything/image').status_code==401

def test_login_cookie_session_csrf(env):
    _,c=env;h=login(c)
    assert 'httponly' in c.post('/api/auth/login',json={'username':'alice','password':'AliceTestPass42!'}).headers['set-cookie'].lower()
    h={'X-CSRF-Token':c.get('/api/auth/session').json()['csrf_token']}
    assert submit(c,{}).status_code==403
    assert c.post('/api/jobs',json={'prompt':'test'},headers={**h,'Origin':'https://attacker.invalid'}).status_code==403
    assert submit(c,h).status_code==201
    assert c.post('/api/auth/logout',headers=h).status_code==200
    assert c.get('/api/auth/session').status_code==401

def test_bad_login_no_registration(env):
    _,c=env
    assert c.post('/api/auth/login',json={'username':'alice','password':'wrong'}).status_code==401
    assert c.post('/api/auth/register',json={}).status_code==404

def test_job_owner_isolation_and_admin_not_image_owner(env):
    app,c=env;h=login(c);j=submit(c,h).json();jid=j['id']
    assert j['status']=='queued'
    assert c.get('/api/jobs').json()['total']==1
    login(c,'bravo','BravoTestPass42!')
    assert c.get('/api/jobs').json()['total']==0
    for path in [f'/api/jobs/{jid}',f'/api/jobs/{jid}/image']:
        assert c.get(path).status_code==404
    h={'X-CSRF-Token':c.get('/api/auth/session').json()['csrf_token']}
    assert c.delete('/api/jobs/'+jid,headers=h).status_code==404
    assert c.post('/api/jobs/'+jid+'/cancel',headers=h).status_code==404
    login(c,'admin','AdminTestPass42!')
    assert c.get('/api/jobs/'+jid).status_code==404

def test_one_active_job_and_cancel(env):
    _,c=env;h=login(c);j=submit(c,h).json()
    assert submit(c,h).status_code==409
    assert c.delete('/api/jobs/'+j['id'],headers=h).status_code==409
    assert c.post('/api/jobs/'+j['id']+'/cancel',headers=h).json()['status']=='cancelled'
    assert c.delete('/api/jobs/'+j['id'],headers=h).status_code==200
    assert submit(c,h).status_code==201

@pytest.mark.parametrize('kwargs',[{'steps':7},{'steps':True},{'seed':-1},{'seed':4294967296},{'prompt':''},{'prompt':'x'*4001},{'width':1024},{'workflow':{}},{'owner_id':'evil'}])
def test_job_input_whitelist(env,kwargs):
    _,c=env;h=login(c)
    assert submit(c,h,**kwargs).status_code==422

def test_pagination_and_filter(env):
    _,c=env;login(c)
    assert c.get('/api/jobs?page=0').status_code==422
    assert c.get('/api/jobs?page_size=1000').status_code==422
    assert c.get('/api/jobs?status=invalid').status_code==422

def test_admin_only_disable_reset_revokes_sessions(env):
    app,c=env;login(c)
    assert c.get('/api/admin/users').status_code==403
    with TestClient(app) as other:
        uh=login(other,'bravo','BravoTestPass42!')
        ah=login(c,'admin','AdminTestPass42!')
        users=c.get('/api/admin/users').json()['items'];uid=next(u['id'] for u in users if u['username']=='bravo')
        assert c.patch('/api/admin/users/'+uid,headers=ah,json={'is_active':False}).status_code==200
        assert other.get('/api/auth/session').status_code==401
        assert c.patch('/api/admin/users/'+uid,headers=ah,json={'is_active':True,'password':'BrandNewPass42!'}).status_code==200
        assert other.post('/api/auth/login',json={'username':'bravo','password':'BravoTestPass42!'}).status_code==401
        assert other.post('/api/auth/login',json={'username':'bravo','password':'BrandNewPass42!'}).status_code==200

def test_admin_create_user_and_no_self_disable(env):
    _,c=env;h=login(c,'admin','AdminTestPass42!')
    assert c.post('/api/admin/users',headers=h,json={'username':'new_user','password':'SecretPass42!'}).status_code==201
    assert c.post('/api/admin/users',headers=h,json={'username':'new_user','password':'SecretPass42!'}).status_code==409
    uid=c.get('/api/auth/session').json()['user']['id']
    assert c.patch('/api/admin/users/'+uid,headers=h,json={'is_active':False}).status_code==409

def test_private_images_and_traversal(env,tmp_path):
    from PIL import Image
    app,c=env;h=login(c);j=submit(c,h).json();path=tmp_path/'images'/f'{j["id"]}.png';Image.new('RGB',(512,512),'red').save(path)
    app.state.db.execute("UPDATE jobs SET status='succeeded',image_path=? WHERE id=?",(str(path),j['id']))
    assert c.get('/api/jobs/'+j['id']+'/image').status_code==200
    assert 'attachment' in c.get('/api/jobs/'+j['id']+'/image?download=true').headers['content-disposition']
    assert c.get('/data/images/'+path.name).status_code==404
    app.state.db.execute('UPDATE jobs SET image_path=? WHERE id=?',('/Windows/win.ini',j['id']))
    assert c.get('/api/jobs/'+j['id']+'/image').status_code==404

def test_gallery_delete_own_image_preserves_other_user(env,tmp_path):
    from PIL import Image
    app,c=env;h=login(c);mine=submit(c,h).json()
    own=tmp_path/'images'/f'{mine["id"]}.png'
    Image.new('RGB',(16,16),'red').save(own)
    app.state.db.execute("UPDATE jobs SET status='succeeded',image_path=? WHERE id=?",(str(own),mine['id']))
    with TestClient(app) as other:
        oh=login(other,'bravo','BravoTestPass42!');theirs=submit(other,oh).json()
        kept=tmp_path/'images'/f'{theirs["id"]}.png'
        Image.new('RGB',(16,16),'blue').save(kept)
        app.state.db.execute("UPDATE jobs SET status='succeeded',image_path=? WHERE id=?",(str(kept),theirs['id']))
        assert other.delete('/api/jobs/'+mine['id'],headers=oh).status_code==404
        assert c.delete('/api/jobs/'+mine['id']).status_code==403
        assert own.exists()
        assert c.delete('/api/jobs/'+mine['id'],headers=h).status_code==200
        assert not own.exists()
        assert c.get('/api/jobs/'+mine['id']).status_code==404
        assert kept.exists()
        assert other.get('/api/jobs/'+theirs['id']+'/image').status_code==200

def test_session_token_is_hashed_and_survives_backend_recreation(env):
    app,c=env;login(c)
    raw=c.cookies.get('moss_session')
    rows=app.state.db.all('SELECT * FROM sessions')
    assert len(rows)==1 and rows[0]['token_hash']!=raw
    new_app=create_app(app.state.settings)
    with TestClient(new_app) as other:
        other.cookies.set('moss_session',raw)
        assert other.get('/api/auth/session').json()['user']['username']=='alice'

def test_disabled_user_queued_job_cancelled(env):
    app,c=env;h=login(c);j=submit(c,h).json()
    ah=login(c,'admin','AdminTestPass42!')
    uid=app.state.db.one('SELECT id FROM users WHERE username=?',('alice',))['id']
    assert c.patch('/api/admin/users/'+uid,headers=ah,json={'is_active':False}).status_code==200
    assert app.state.db.one('SELECT status FROM jobs WHERE id=?',(j['id'],))['status']=='cancelled'

def test_login_rate_limit(env):
    _,c=env
    for _ in range(20):
        assert c.post('/api/auth/login',json={'username':'alice','password':'wrong'}).status_code==401
    assert c.post('/api/auth/login',json={'username':'alice','password':'wrong'}).status_code==429
