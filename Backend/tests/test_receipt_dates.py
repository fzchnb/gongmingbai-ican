import json
import pytest
import agent
from receipt_dates import suggest, text_days
from test_projects import client, setup, FIELDS
from test_workflows import ledger_setup, get_ledger, decision
import main


@pytest.mark.parametrize('date_value,facts,evidence,start,expected,source', [
    ('2026-10-25',{'screenshot_date':'2026-10-24'},'', '2026-10-20','2026-10-25','transfer'),
    (None,{'screenshot_date':'2026-10-24','excerpt':'2026-10-20工钱'},'', '2026-10-20','2026-10-24','screenshot'),
    (None,{'visible_text':'王师傅，2026年10月23日的工钱麻烦安排一下。\n转你40元。'},'', '2026-10-20','2026-10-23','message'),
    (None,{'excerpt':'2026/10/23 的工钱，2026.10.23 再核一下'},'', '2026-10-20','2026-10-23','message'),
    (None,{'excerpt':'2026-10-20至2026-10-24工钱'},'2026年10月25日转40', '2026-10-20','2026-10-25','message'),
    (None,{'excerpt':'2026-10-20至2026-10-24工钱'},'', '2026-10-20','2026-10-20','ledger_start'),
    (None,{'excerpt':'刚转了40，10月25日09:20','explanation':'AI说2026-10-24'},'', '2026-10-20','2026-10-20','ledger_start'),
    ('2099-01-01',{'screenshot_date':'2026-02-30','excerpt':'2099年1月1日转'},'', '2026-10-20','2026-10-20','ledger_start'),
    (None,{},'',None,None,None),
    (None,{'excerpt':'2026-10-23 转40'},'',None,'2026-10-23','message'),
])
def test_date_priority_and_no_fabrication(monkeypatch,date_value,facts,evidence,start,expected,source):
    monkeypatch.setattr(agent,'today',lambda:'2026-10-26')
    receipt={'id':'pending','status':'pending','date':date_value,'evidence':evidence,'amount_fen':4000}
    result=suggest(receipt,facts,start)
    assert result['date']==expected and result['date_source']==source
    assert result['date_needs_confirmation']==(source!='transfer')
    assert '核对' in result['date_hint'] or '请填写' in result['date_hint']
    assert receipt['date']==date_value  # Read-time default never writes a payment.


def date_report(c,h,p,monkeypatch,facts):
    monkeypatch.setattr(main.ai,'vision',lambda *_:facts)
    asset=c.post('/api/v1/assets?project_id='+p+'&purpose=reconcile',headers=h,
        files={'file':('screen.png',main.uid().encode(),'image/png')}).json()
    task=c.post('/api/v1/tasks',headers=h,json={'type':'reconcile','project_id':p,'asset_id':asset['id'],
        'request_id':main.uid()}).json()
    if task['status']=='queued': main.run_task(task)
    response=c.post('/api/v1/reports',headers=h,json={'task_id':task['id'],'excerpt':facts.get('excerpt','')})
    assert response.status_code==200,response.text
    return response.json()


def test_screenshot_message_date_prefilled_and_requires_person_confirmation(client,monkeypatch):
    c=client;h,owner,p=ledger_setup(c)
    facts={'excerpt':'2026年10月24日的工钱麻烦付一下。\n已转40元',
           'payments':[{'amount':'40','date':None,'kind':'transfer','evidence':'已转40元'}]}
    report=date_report(c,h,p,monkeypatch,facts)
    receipt=report['receipts'][0]
    assert receipt['date']=='2026-10-24' and receipt['date_source']=='message'
    assert get_ledger(c,h,p)['totals']['balance_fen']==25000
    assert decision(c,h,report,date=receipt['date'],confirmed=False).status_code==400
    result=decision(c,h,report,date=receipt['date']).json()
    assert result['totals']['balance_fen']==21000
    assert result['receipts'][0]['date']=='2026-10-24'
    assert decision(c,h,report,date=receipt['date']).status_code==200
    assert len(get_ledger(c,h,p)['payments'])==2


def test_no_date_uses_current_project_earliest_confirmed_work_and_restores_legacy_without_writes(client,monkeypatch):
    c=client;h,owner,p=ledger_setup(c)
    # Earlier date inserted after a later entry; unconfirmed drafts and other
    # projects must not affect the current project's start.
    fields={**FIELDS,'date':'2026-10-20','advance':'0'}
    draft=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':fields}).json()
    c.post('/api/v1/drafts/'+draft['id']+'/confirm',headers=h,json=fields).raise_for_status()
    c.post('/api/v1/drafts',headers=h,json={'project_id':p,'fields':{**fields,'date':'2026-10-01'}}).raise_for_status()
    other=c.post('/api/v1/projects',headers=h,json={'name':'另一个项目','boss':'另一老板'}).json()
    before={**fields,'date':'2026-09-01'}
    d=c.post('/api/v1/drafts',headers=h,json={'project_id':other['id'],'fields':before}).json()
    c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json=before).raise_for_status()
    report=date_report(c,h,p,monkeypatch,{'excerpt':'转了40', 'payments':[{'amount':'40','date':None}]})
    assert report['receipts'][0]['date']=='2026-10-20'
    assert report['receipts'][0]['date_source']=='ledger_start'
    stored=main.store.get(owner,'reports',report['id'])
    for key in ('date_source','date_hint'): stored['receipts'][0].pop(key,None)
    stored['receipts'][0]['date']=None
    main.store.put(owner,'reports',stored)
    snapshot=json.dumps(stored,sort_keys=True)
    recovered=c.get('/api/v1/projects/'+p+'/workspace',headers=h).json()['pending_reports'][0]
    assert recovered['receipts'][0]['date']=='2026-10-20'
    assert json.dumps(main.store.get(owner,'reports',report['id']),sort_keys=True)==snapshot
    # Person may correct the default. It is their confirmed date that is saved.
    result=decision(c,h,recovered,date='2026-10-26').json()
    assert result['receipts'][0]['date']=='2026-10-26'
    assert c.get('/api/v1/reports/'+report['id'],headers=h).json()['receipts'][0]['date']=='2026-10-26'


def test_empty_project_no_date_stays_empty_and_no_receipt_on_rejection(client,monkeypatch):
    c=client;h,_,p=setup(c)
    report=date_report(c,h,p,monkeypatch,{'payments':[{'amount':'40','date':None,'kind':'promise'}]})
    assert report['receipts'][0]['date'] is None
    assert decision(c,h,report,date=None).status_code==422
    assert decision(c,h,report,received=False).json()['receipts'][0]['status']=='not_received'
    assert not get_ledger(c,h,p)['payments']
