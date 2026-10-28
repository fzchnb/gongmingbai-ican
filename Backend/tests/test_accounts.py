import pytest
from fastapi.testclient import TestClient
import main
from store import Store

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SECRET_KEY', raising=False)
    monkeypatch.setattr(main, 'store', Store())
    return TestClient(main.app)

def test_register_login_logout_and_guest_binding(client):
    c=client
    g=c.post('/api/v1/auth/guest').json()
    h={'Authorization':'Bearer '+g['access_token']}
    project=c.post('/api/v1/projects',headers=h,json={'name':'游客账本','boss':'测试老板'}).json()
    credentials={'phone':'19900000001','password':'TestPassword2026!'}
    r=c.post('/api/v1/auth/register',headers=h,json=credentials)
    assert r.status_code==200
    assert r.json()['user']['id']==g['user']['id']
    h={'Authorization':'Bearer '+r.json()['access_token']}
    assert c.get('/api/v1/auth/me',headers=h).json()['is_anonymous'] is False
    assert c.get('/api/v1/projects',headers=h).json()[0]['id']==project['id']
    assert c.post('/api/v1/auth/register',json=credentials).status_code==409
    assert c.post('/api/v1/auth/login',json={**credentials,'password':'WrongPassword!'}).status_code==401
    assert c.post('/api/v1/auth/logout',headers=h).status_code==200
    assert c.get('/api/v1/projects',headers=h).status_code==401
    login=c.post('/api/v1/auth/login',json=credentials)
    assert login.status_code==200
    h={'Authorization':'Bearer '+login.json()['access_token']}
    assert c.get('/api/v1/projects',headers=h).status_code==200
    with main.store.db() as db:
        assert credentials['password'] not in str(db.execute('SELECT * FROM accounts').fetchall())

def test_invalid_phone_and_short_password(client):
    for body in [{'phone':'abc','password':'LongPassword123'},{'phone':'19900000001','password':'123'}]:
        assert client.post('/api/v1/auth/register',json=body).status_code==422

def test_upstream_failure_is_readable_with_cors(client,monkeypatch):
    import httpx
    def fail(request):
        raise httpx.ConnectError('test outage',request=request)
    monkeypatch.setattr(main.store,'cloud',True)
    monkeypatch.setattr(main.store,'client',httpx.Client(transport=httpx.MockTransport(fail)))
    r=client.get('/api/v1/projects',headers={'Authorization':'Bearer test','Origin':'http://127.0.0.1:5173'})
    assert r.status_code==503
    assert r.headers['access-control-allow-origin']=='http://127.0.0.1:5173'
    assert r.headers['access-control-expose-headers']=='Content-Disposition'
