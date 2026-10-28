import io
import zipfile
import pytest
from fastapi.testclient import TestClient
import main
from store import Store
from domain import calculate, cents, compare

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SECRET_KEY', raising=False)
    monkeypatch.setattr(main, 'store', Store())
    return TestClient(main.app)

def guest(c):
    return {'Authorization':'Bearer '+c.post('/api/v1/auth/guest').json()['access_token']}

def test_money():
    f={'date':'2026-10-23','days':'1','day_rate':'350','overtime_hours':'2','overtime_rate':'30','advance':'100'}
    v=calculate(f)
    assert v['balance_fen']==31000
    assert compare(v,{'wage':'380','advance':'100','balance':'280'})[2]['difference_fen']==3000
    f['overtime_rate']=None
    assert calculate(f)['missing']==['加班单价']
    assert cents('0.005')==1
    for value in ['NaN','Infinity','-1']:
        with pytest.raises(ValueError): cents(value)

def test_ledger_isolation_idempotency_export(client):
    c=client; h=guest(c); other=guest(c)
    p=c.post('/api/v1/projects',headers=h,json={'name':'万达三期','boss':'王师傅'}).json()['id']
    f={'date':'2026-10-23','days':'1','day_rate':'350','overtime_hours':'2','overtime_rate':'30','advance':'100'}
    draft=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':f}).json()
    for _ in range(2): assert c.post('/api/v1/drafts/'+draft['id']+'/confirm',headers=h,json=f).status_code==200
    ledger=c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()
    assert ledger['totals']=={'wage_fen':41000,'advance_fen':10000,'balance_fen':31000}
    assert len(ledger['entries'])==1
    assert c.get('/api/v1/projects/'+p+'/ledger',headers=other).status_code==404
    assert c.get('/api/v1/projects').status_code==401
    z=c.get('/api/v1/projects/'+p+'/export',headers=h)
    assert 'ledger.csv' in zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    pay={'project_id':p,'date':'2026-10-23','amount':'310','request_id':'same-payment-001'}
    for _ in range(2): assert c.post('/api/v1/payments',headers=h,json=pay).status_code==200
    assert c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()['totals']['balance_fen']==0

def test_edit_keeps_history(client):
    c=client;h=guest(c)
    p=c.post('/api/v1/projects',headers=h,json={'name':'项目','boss':'老板'}).json()['id']
    f={'date':'2026-10-23','days':'1','day_rate':'350','advance':'100'}
    d=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':f}).json()
    c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json=f)
    e=c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()['entries'][0]
    f.update(day_rate='360',advance='0')
    assert c.patch('/api/v1/entries/'+e['id'],headers=h,json=f).status_code==200
    assert c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()['totals']['balance_fen']==36000
    events=c.get('/api/v1/projects/'+p+'/timeline',headers=h).json()
    assert next(r for r in events if 'before' in r)['before']['wage_fen']==35000

def test_reconcile_does_not_receive_payment(client,monkeypatch):
    # Provider is stubbed here to test orchestration only, not live AI quality.
    c=client;h=guest(c)
    p=c.post('/api/v1/projects',headers=h,json={'name':'项目','boss':'老板'}).json()['id']
    f={'date':'2026-10-23','days':'1','day_rate':'350','overtime_hours':'2','overtime_rate':'30','advance':'100'}
    d=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':f}).json()
    c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json=f)
    a=c.post('/api/v1/assets?project_id='+p,headers=h,files={'file':('test.png',b'test-image','image/png')}).json()
    monkeypatch.setattr(main.ai,'vision',lambda *args:{'wage':'380','advance':'100','balance':'280','excerpt':'明天转280'})
    t=c.post('/api/v1/tasks',headers=h,json={'project_id':p,'type':'reconcile','asset_id':a['id'],'request_id':'reconcile-test-001'}).json()
    main.run_task(t)
    body={'task_id':t['id'],'date':'2026-10-23','wage':'380','advance':'100','balance':'280','excerpt':'明天转280'}
    r=c.post('/api/v1/reports',headers=h,json=body)
    assert r.status_code==200 and r.json()['rows'][2]['difference_fen']==3000
    assert c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()['totals']['advance_fen']==10000
    body.update(wage=None,advance=None,balance=None)
    assert c.post('/api/v1/reports',headers=h,json=body).status_code==422

def test_unknown_rate_and_failed_ai(client,monkeypatch):
    c=client;h=guest(c);p=c.post('/api/v1/projects',headers=h,json={'name':'项目','boss':'老板'}).json()['id']
    f={'date':'2026-10-23','days':'1','day_rate':'350','overtime_hours':'2','advance':'0'}
    d=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':f}).json()
    assert c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json=f).status_code==422
    monkeypatch.delenv('DASHSCOPE_API_KEY',raising=False)
    t=c.post('/api/v1/tasks',headers=h,json={'project_id':p,'type':'work','text':'今天一天350','request_id':'test-task-001'}).json()
    main.run_task(t)
    result=c.get('/api/v1/tasks/'+t['id'],headers=h).json()
    assert result['status']=='failed' and '密钥' in result['error']
    assert c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()['entries']==[]
