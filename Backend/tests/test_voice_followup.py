import json
import pytest
import main
import ai
from test_projects import client, setup
from test_workflows import ledger_setup, recognize, decision


def test_voice_tasks_persist_transcription_and_real_processing_stages(client,monkeypatch):
    c=client;h,owner,p=setup(c)
    a=c.post('/api/v1/assets?project_id='+p+'&purpose=ai_input',headers=h,
        files={'file':('voice.mp3',b'voice-test','audio/mpeg')}).json()
    t=c.post('/api/v1/tasks',headers=h,json={'project_id':p,'type':'work','asset_id':a['id'],'request_id':main.uid()}).json()
    def transcribe(*_):
        assert main.store.get(owner,'tasks',t['id'])['stage']=='正在把录音转成文字…'
        return '今天一天350元，借支100元'
    def parse(text,today,context):
        current=main.store.get(owner,'tasks',t['id'])
        assert current['stage']=='正在整理记工草稿…' and current['transcript']==text
        return {'date':'2026-10-25','days':'1','day_rate':'350','advance':'100'}
    monkeypatch.setattr(main.ai,'transcribe',transcribe);monkeypatch.setattr(main.ai,'parse',parse)
    main.run_task(t)
    result=c.get('/api/v1/tasks/'+t['id'],headers=h).json()
    assert result['status']=='completed' and result['result']['calculation']['balance_fen']==25000
    assert result['transcript']=='今天一天350元，借支100元'
    assert c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()['entries']==[]


@pytest.mark.parametrize('state,expected',[('pending','verify_receipt'),('unpaid','payment_followup'),('settled','settled_ack'),('overpaid','verify_overpayment')])
def test_followup_fallback_matches_receipt_and_latest_balance(client,monkeypatch,state,expected):
    c=client;h,owner,p=ledger_setup(c)
    _,_,r,_=recognize(c,h,p,monkeypatch)
    if state!='pending':decision(c,h,r,received=False)
    if state in ('settled','overpaid'):
        c.post('/api/v1/payments',headers=h,json={'project_id':p,'amount':'250' if state=='settled' else '300','date':'2026-10-25','request_id':main.uid()})
    def failed(*_):raise RuntimeError('test unavailable')
    monkeypatch.setattr(main.ai,'message_style',failed)
    result=c.get('/api/v1/reports/'+r['id']+'/message',headers=h).json()
    assert result['intent']==expected and result['generated_by']=='fallback'
    if state=='unpaid':assert '什么时候能付' in result['text'] and '250元' in result['text']
    elif state=='settled':assert '已经结清' in result['text'] and '谢谢' in result['text'] and '什么时候' not in result['text']
    elif state=='pending':assert '核实' in result['text'] and '什么时候能付' not in result['text']
    else:assert '多收50元' in result['text'] and '什么时候能付' not in result['text']


def test_money_changes_while_generating_does_not_send_stale_payment_request(client,monkeypatch):
    c=client;h,owner,p=ledger_setup(c)
    _,_,r,_=recognize(c,h,p,monkeypatch);decision(c,h,r,received=False)
    def style(*_):
        main.store.put(owner,'payments',main.item(project_id=p,date='2026-10-25',amount_fen=25000,type='received'))
        return {'opening':'接着刚才的消息。','closing':'麻烦安排剩余工资，什么时候付？'}
    monkeypatch.setattr(main.ai,'message_style',style)
    result=c.get('/api/v1/reports/'+r['id']+'/message',headers=h).json()
    assert result['intent']=='settled_ack' and result['totals']['balance_fen']==0
    assert '谢谢' in result['text'] and '什么时候付' not in result['text']


def test_model_followup_requires_payment_action_and_settled_reply_cannot_request_debt(monkeypatch):
    report={'receipts':[]}
    monkeypatch.setattr(ai,'call',lambda *_:json.dumps({'opening':'接着刚才的消息。','closing':'请再看看账。'}))
    with pytest.raises(ValueError,match='付款请求'):
        ai.message_style({'totals':{'balance_fen':28400}},report)
    monkeypatch.setattr(ai,'call',lambda *_:json.dumps({'opening':'收到。','closing':'剩余工钱什么时候付？'}))
    with pytest.raises(ValueError,match='不能催款'):
        ai.message_style({'totals':{'balance_fen':0}},report)
    monkeypatch.setattr(ai,'call',lambda *_:json.dumps({'opening':'王师傅刚回过。','closing':'麻烦安排余款，什么时候付？'}))
    with pytest.raises(ValueError,match='直接对收信人'):
        ai.message_style({'project':{'boss':'王师傅'},'totals':{'balance_fen':28400}},report)


def test_payment_followup_also_requests_payment_time(client,monkeypatch):
    c=client;h,_,p=ledger_setup(c)
    _,_,r,_=recognize(c,h,p,monkeypatch);decision(c,h,r)
    monkeypatch.setattr(main.ai,'message_style',lambda *_:{'opening':'接着刚才的回复。','closing':'麻烦您安排一下剩余工钱。'})
    result=c.get('/api/v1/reports/'+r['id']+'/message',headers=h).json()
    assert '210元' in result['text'] and '什么时候能付' in result['text']


def test_settled_reply_does_not_repeat_an_old_partial_transfer(client,monkeypatch):
    c=client;h,_,p=ledger_setup(c)
    _,_,r,_=recognize(c,h,p,monkeypatch);decision(c,h,r)
    c.post('/api/v1/payments',headers=h,json={'project_id':p,'amount':'210','date':'2026-10-25','request_id':main.uid()})
    monkeypatch.setattr(main.ai,'message_style',lambda *_:{'opening':'收到，我这边也记好了。','closing':'谢谢您。'})
    result=c.get('/api/v1/reports/'+r['id']+'/message',headers=h).json()
    assert result['intent']=='settled_ack' and '已经结清' in result['text']
    assert '40元' not in result['text'] and '350元' in result['text']
