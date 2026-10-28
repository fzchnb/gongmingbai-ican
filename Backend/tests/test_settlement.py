import pytest
import main
from domain import calculate
from test_projects import client, setup


FIELDS = {'date':'2026-10-25','days':'1','day_rate':'284','advance':'0'}


def save(c,h,p,fields):
    draft=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':fields})
    assert draft.status_code==200,draft.text
    result=c.post('/api/v1/drafts/'+draft.json()['id']+'/confirm',headers=h,json=fields)
    assert result.status_code==200,result.text
    return result.json()


def ledger(c,h,p):
    return c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()


def task(c,h,p,text,**extra):
    value=c.post('/api/v1/tasks',headers=h,json={'type':'work','project_id':p,'text':text,
        'request_id':main.uid(),**extra}).json()
    main.run_task(value)
    result=c.get('/api/v1/tasks/'+value['id'],headers=h).json()
    assert result['status']=='completed',result
    return result['result']


def test_full_284_receipt_then_new_settled_work_stays_zero(client,monkeypatch):
    c=client;h,owner,p=setup(c)
    save(c,h,p,FIELDS)
    monkeypatch.setattr(main.ai,'vision',lambda *_:{'wage':None,'advance':None,'balance':None,
        'payments':[{'amount':'284','date':'2026-10-25','kind':'transfer','evidence':'转账284元'}]})
    a=c.post('/api/v1/assets?project_id='+p+'&purpose=reconcile',headers=h,
        files={'file':('settlement.png',b'284-transfer','image/png')}).json()
    t=c.post('/api/v1/tasks',headers=h,json={'type':'reconcile','project_id':p,'asset_id':a['id'],'request_id':main.uid()}).json()
    main.run_task(t)
    r=c.post('/api/v1/reports',headers=h,json={'task_id':t['id']}).json()
    url='/api/v1/reports/'+r['id']+'/receipts/'+r['receipts'][0]['id']
    for _ in range(2):
        result=c.post(url,headers=h,json={'received':True,'confirmed':True,'amount':'284','date':'2026-10-25'})
        assert result.status_code==200 and result.json()['totals']['balance_fen']==0
    assert c.get('/api/v1/reports/'+r['id'],headers=h).json()['rows'][2]['mine_fen']==28400
    seen=[]
    def parse(*args):
        seen.append(args[2]);return {**FIELDS,'settled':True}
    monkeypatch.setattr(main.ai,'parse',parse)
    draft=task(c,h,p,'又干一天284元，工资已经结清')
    assert seen[0]['totals']['balance_fen']==0
    assert seen[0]['reconciliations'][0]['rows_are_historical_snapshot'] is True
    assert draft['calculation']['balance_fen']==0 and draft['calculation']['received_fen']==28400
    assert len(ledger(c,h,p)['entries'])==1
    for _ in range(2):
        response=c.post('/api/v1/drafts/'+draft['id']+'/confirm',headers=h,json=draft['fields'])
        assert response.status_code==200
    value=ledger(c,h,p)
    assert value['totals']=={'wage_fen':56800,'advance_fen':56800,'balance_fen':0}
    assert len(value['entries'])==2 and len(value['payments'])==2
    report=c.get('/api/v1/projects/'+p+'/workspace',headers=h).json()['latest_report']
    assert report['totals']['balance_fen']==0 and report['rows'][2]['mine_fen']==28400


def test_settlement_deducts_advance_and_partial_payment_is_separate(client):
    c=client;h,_,p=setup(c)
    fields={**FIELDS,'day_rate':'350','advance':'100','received':'50'}
    d=save(c,h,p,fields)
    assert d['calculation']['received_fen']==5000
    assert ledger(c,h,p)['totals']['balance_fen']==20000
    entry=ledger(c,h,p)['entries'][0]
    response=c.patch('/api/v1/entries/'+entry['id'],headers=h,json={**fields,'settled':True})
    assert response.status_code==200
    value=ledger(c,h,p)
    assert value['totals']=={'wage_fen':35000,'advance_fen':35000,'balance_fen':0}
    assert sorted(p['amount_fen'] for p in value['payments'])==[10000,25000]


def test_this_work_settled_does_not_clear_other_unpaid_work(client):
    c=client;h,_,p=setup(c)
    save(c,h,p,{**FIELDS,'day_rate':'100'})
    save(c,h,p,{**FIELDS,'settled':True})
    assert ledger(c,h,p)['totals']=={'wage_fen':38400,'advance_fen':28400,'balance_fen':10000}


def test_edit_and_undo_settlement_only_adjusts_this_entries_payment(client):
    c=client;h,_,p=setup(c)
    save(c,h,p,{**FIELDS,'settled':True})
    c.post('/api/v1/payments',headers=h,json={'project_id':p,'amount':'40','date':'2026-10-25','request_id':main.uid()})
    before=ledger(c,h,p)
    unrelated=next(v for v in before['payments'] if not v.get('entry_id'))
    entry=before['entries'][0]
    assert c.patch('/api/v1/entries/'+entry['id'],headers=h,json={**FIELDS,'day_rate':'300','settled':True}).status_code==200
    assert ledger(c,h,p)['totals']['balance_fen']==-4000
    assert c.patch('/api/v1/entries/'+entry['id'],headers=h,json={**FIELDS,'day_rate':'300','settled':False,'received':'0'}).status_code==200
    after=ledger(c,h,p)
    assert after['totals']['balance_fen']==26000 and len(after['payments'])==1
    assert after['payments'][0]==unrelated


def test_settlement_correction_is_still_a_draft_and_can_be_undone(client,monkeypatch):
    c=client;h,_,p=setup(c)
    monkeypatch.setattr(main.ai,'parse',lambda *_:FIELDS)
    d=task(c,h,p,'今天一天284元')
    monkeypatch.setattr(main.ai,'revise',lambda *_:{'changes':{'settled':True},'reply':'已标明本笔收到全部工资，请核对。'})
    d=task(c,h,p,'这笔已经结清',type='revise',draft_id=d['id'],fields=d['fields'],expected_revision=0)
    assert d['calculation']['received_fen']==28400 and not ledger(c,h,p)['payments']
    monkeypatch.setattr(main.ai,'revise',lambda *_:{'changes':{'settled':False,'received':'0'},'reply':'改为尚未收到。'})
    d=task(c,h,p,'说错了，还没收到',type='revise',draft_id=d['id'],fields=d['fields'],expected_revision=1)
    assert d['calculation']['balance_fen']==28400
    assert c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json=d['fields']).status_code==200
    assert not ledger(c,h,p)['payments']


def test_unknown_wage_cannot_become_historic_284_or_be_confirmed(client,monkeypatch):
    c=client;h,_,p=setup(c)
    save(c,h,p,FIELDS)
    monkeypatch.setattr(main.ai,'parse',lambda *_:{'date':'2026-10-25','days':None,'day_rate':None,'settled':True})
    d=task(c,h,p,'又干一件活，工资也结好了')
    assert '日单价' in d['calculation']['missing'] and d['calculation']['received_fen'] is None
    assert c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json=d['fields']).status_code==422
    assert ledger(c,h,p)['totals']['balance_fen']==28400


def test_explicit_payment_date_and_future_date_validation(client):
    c=client;h,_,p=setup(c)
    save(c,h,p,{**FIELDS,'date':'2026-10-24','settled':True,'received_date':'2026-10-25'})
    assert ledger(c,h,p)['payments'][0]['date']=='2026-10-25'
    with pytest.raises(ValueError,match='不能晚于今天'):
        calculate({**FIELDS,'settled':True,'received_date':'2099-01-01'})


def test_older_clients_omitting_payment_fields_do_not_erase_known_settlement(client):
    c=client;h,_,p=setup(c)
    fields={**FIELDS,'settled':True}
    draft=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':fields}).json()
    assert c.post('/api/v1/drafts/'+draft['id']+'/confirm',headers=h,json=FIELDS).status_code==200
    entry=ledger(c,h,p)['entries'][0]
    assert c.patch('/api/v1/entries/'+entry['id'],headers=h,json={**FIELDS,'note':'补备注'}).status_code==200
    assert ledger(c,h,p)['totals']['balance_fen']==0


def test_failed_confirmation_does_not_save_wage_or_receipt_partially(client,monkeypatch):
    c=client;h,owner,p=setup(c)
    d=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':{**FIELDS,'settled':True}}).json()
    def fail(*_):
        raise RuntimeError('test storage unavailable')
    monkeypatch.setattr(main.store,'batch',fail)
    with pytest.raises(RuntimeError):
        c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json=d['fields'])
    assert not ledger(c,h,p)['entries'] and not ledger(c,h,p)['payments']
    assert not main.store.get(owner,'drafts',d['id'])['confirmed']
