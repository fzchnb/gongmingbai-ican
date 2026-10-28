import io
import json
import zipfile
import pytest
from test_projects import client, setup, FIELDS
import main


def ledger_setup(c):
    h, owner, p=setup(c)
    d=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':FIELDS}).json()
    assert c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json=FIELDS).status_code==200
    return h,owner,p


def recognize(c,h,p,monkeypatch,kind='transfer',image=b'test-transfer-40',transaction=''):
    seen=[]
    def vision(data,mime,context):
        seen.append(context)
        return {'wage':None,'advance':None,'balance':None,'date':None,'excerpt':'师傅：转了40，核一下',
                'explanation':'本项目已记一天350、借支100，本次40元请核实到账。',
                'payments':[{'amount':'40','date':'2026-10-25','kind':kind,'evidence':'这笔转账40元',
                             'transaction_id':transaction}]}
    monkeypatch.setattr(main.ai,'vision',vision)
    a=c.post('/api/v1/assets?project_id='+p+'&purpose=reconcile',headers=h,
        files={'file':('transfer.png',image,'image/png')}).json()
    t=c.post('/api/v1/tasks',headers=h,json={'type':'reconcile','project_id':p,'asset_id':a['id'],
        'request_id':'recognize-'+str(len(main.store.list('', 'tasks')))+'-'+main.uid()}).json()
    if t['status']=='queued':
        main.run_task(t)
    assert c.get('/api/v1/tasks/'+t['id'],headers=h).json()['status']=='completed'
    r=c.post('/api/v1/reports',headers=h,json={'task_id':t['id'],'excerpt':'本次40元'} )
    assert r.status_code==200,r.text
    return a,t,r.json(),seen


def decision(c,h,r,**changes):
    body={'received':True,'confirmed':True,'amount':'40','date':'2026-10-25',**changes}
    return c.post('/api/v1/reports/'+r['id']+'/receipts/'+r['receipts'][0]['id'],headers=h,json=body)


def get_ledger(c,h,p):
    return c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()


def test_shared_memory_40_receipt_confirmation_recovery_and_one_archive(client,monkeypatch):
    c=client;h,owner,p=ledger_setup(c)
    a,t,r,seen=recognize(c,h,p,monkeypatch)
    assert seen[0]['project']['id']==p and seen[0]['totals']['balance_fen']==25000
    assert seen[0]['entries'][0]['date']=='2026-10-25'
    assert 'source_text' not in seen[0]['entries'][0] and 'note' not in seen[0]['entries'][0]['fields']
    assert seen[0]['payments'][0]['amount_fen']==10000
    assert main.store.get(owner,'tasks',t['id'])['context']['ledger_version']==seen[0]['ledger_version']
    assert r['status']=='awaiting_receipt' and r['receipts'][0]['status']=='pending'
    assert get_ledger(c,h,p)['totals']['balance_fen']==25000
    assert len(c.get('/api/v1/projects/'+p+'/timeline',headers=h).json())==1
    workspace=c.get('/api/v1/projects/'+p+'/workspace',headers=h).json()
    assert workspace['pending_reports'][0]['id']==r['id'] and workspace['active_task'] is None
    with zipfile.ZipFile(io.BytesIO(c.get('/api/v1/projects/'+p+'/export',headers=h).content)) as z:
        assert json.loads(z.read('manifest.json'))==[]
    assert decision(c,h,r,confirmed=False).status_code==400
    assert decision(c,h,r,date=None).status_code==422
    assert decision(c,h,r,date='2099-01-01').status_code==422
    assert decision(c,h,r).json()['totals']['balance_fen']==21000
    assert decision(c,h,r).status_code==200
    assert len(get_ledger(c,h,p)['payments'])==2
    events=c.get('/api/v1/projects/'+p+'/timeline',headers=h).json()
    assert len([e for e in events if e.get('report_id')==r['id']])==1
    assert not c.get('/api/v1/projects/'+p+'/workspace',headers=h).json()['pending_reports']
    with zipfile.ZipFile(io.BytesIO(c.get('/api/v1/projects/'+p+'/export',headers=h).content)) as z:
        manifest=json.loads(z.read('manifest.json'))
        assert len(manifest)==1 and z.read(manifest[0]['archive_path'])==b'test-transfer-40'
    _,_,second,_=recognize(c,h,p,monkeypatch)
    assert second['id']==r['id'] and second['status']=='completed'
    assert get_ledger(c,h,p)['totals']['balance_fen']==21000
    memory=c.get('/api/v1/projects/'+p+'/memory',headers=h).json()
    assert memory['totals']['balance_fen']==21000 and memory['reconciliations'][0]['receipts'][0]['status']=='confirmed'


def test_promise_never_auto_receives_and_owner_isolation(client,monkeypatch):
    c=client;h,_,p=ledger_setup(c)
    _,_,r,_=recognize(c,h,p,monkeypatch,kind='promise')
    other,_,other_project=setup(c)
    assert decision(c,other,r).status_code==404
    assert c.get('/api/v1/projects/'+p+'/memory',headers=other).status_code==404
    assert c.get('/api/v1/projects/'+other_project+'/memory',headers=other).json()['totals']['wage_fen']==0
    assert get_ledger(c,h,p)['totals']['balance_fen']==25000
    value=decision(c,h,r,received=False).json()
    assert value['status']=='completed' and value['receipts'][0]['status']=='not_received'
    assert get_ledger(c,h,p)['totals']['balance_fen']==25000
    assert decision(c,h,r).json()['receipts'][0]['status']=='not_received'


def test_possible_duplicate_requires_extra_confirmation_and_transaction_id_dedupes(client,monkeypatch):
    c=client;h,_,p=ledger_setup(c)
    c.post('/api/v1/payments',headers=h,json={'project_id':p,'date':'2026-10-25','amount':'40','request_id':'manual-forty-before-check'})
    _,_,r,_=recognize(c,h,p,monkeypatch,transaction='transfer-001')
    assert decision(c,h,r).status_code==409
    assert decision(c,h,r,confirm_duplicate=True).status_code==200
    assert get_ledger(c,h,p)['totals']['balance_fen']==17000
    _,_,second,_=recognize(c,h,p,monkeypatch,image=b'another-image-same-transfer',transaction='transfer-001')
    assert decision(c,h,second,amount='45').status_code==422
    value=decision(c,h,second).json()
    assert value['receipts'][0]['status']=='already_recorded'
    assert get_ledger(c,h,p)['totals']['balance_fen']==17000


def test_unfinished_recognition_restores_and_cancel_does_not_archive(client,monkeypatch):
    c=client;h,_,p=ledger_setup(c)
    monkeypatch.setattr(main.ai,'vision',lambda *_:{'wage':'350','advance':'100','balance':'250'})
    a=c.post('/api/v1/assets?project_id='+p+'&purpose=reconcile',headers=h,
        files={'file':('screen.png',b'pending-image','image/png')}).json()
    t=c.post('/api/v1/tasks',headers=h,json={'type':'reconcile','project_id':p,'asset_id':a['id'],'request_id':'unfinished-process'}).json()
    main.run_task(t)
    assert c.get('/api/v1/projects/'+p+'/workspace',headers=h).json()['active_task']['id']==t['id']
    assert c.post('/api/v1/tasks/'+t['id']+'/dismiss',headers=h).status_code==200
    assert c.get('/api/v1/projects/'+p+'/workspace',headers=h).json()['active_task'] is None
    assert len(c.get('/api/v1/projects/'+p+'/timeline',headers=h).json())==1


def test_project_context_is_used_for_new_work_and_revisions(client,monkeypatch):
    c=client;h,_,p=ledger_setup(c)
    seen=[]
    def parse(text,today,context):
        seen.append(context);return FIELDS
    monkeypatch.setattr(main.ai,'parse',parse)
    t=c.post('/api/v1/tasks',headers=h,json={'type':'work','project_id':p,'text':'接着记','request_id':'work-context-shared'}).json()
    main.run_task(t)
    draft=c.get('/api/v1/tasks/'+t['id'],headers=h).json()['result']
    def revise(fields,text,today,history,context):
        seen.append(context);return {'changes':{'advance':'80'},'reply':'已改借支'}
    monkeypatch.setattr(main.ai,'revise',revise)
    t=c.post('/api/v1/tasks',headers=h,json={'type':'revise','project_id':p,'draft_id':draft['id'],
        'text':'借支80','request_id':'revise-context-shared'}).json()
    main.run_task(t)
    assert len(seen)==2 and seen[0]['ledger_version']==seen[1]['ledger_version']
    assert seen[1]['totals']['balance_fen']==25000


def test_message_uses_current_facts_and_confirmed_receipt(client,monkeypatch):
    c=client;h,_,p=ledger_setup(c)
    _,_,r,_=recognize(c,h,p,monkeypatch)
    decision(c,h,r)
    seen=[]
    def style(context,report):
        seen.append(context);return {'opening':'接着刚才的回复，我把余款整理好了。','closing':'剩余工钱麻烦安排一下，方便什么时候付？'}
    monkeypatch.setattr(main.ai,'message_style',style)
    message=c.get('/api/v1/reports/'+r['id']+'/message',headers=h).json()
    assert '210元' in message['text'] and '140元' in message['text'] and '40元我确认收到了' in message['text']
    assert message['generated_by']=='ai' and seen[0]['totals']['balance_fen']==21000
    assert message['intent']=='payment_followup' and '什么时候付' in message['text']


def test_no_partial_payment_when_atomic_save_fails(client,monkeypatch):
    c=client;h,owner,p=ledger_setup(c)
    _,_,r,_=recognize(c,h,p,monkeypatch)
    def fail(*_):
        raise RuntimeError('test storage outage')
    monkeypatch.setattr(main.store,'batch',fail)
    with pytest.raises(RuntimeError):
        main.reconciliation.decide(owner,r['id'],r['receipts'][0]['id'],{
            'received':True,'confirmed':True,'amount':'40','date':'2026-10-25'})
    assert get_ledger(c,h,p)['totals']['balance_fen']==25000
    assert main.store.get(owner,'reports',r['id'])['receipts'][0]['status']=='pending'
