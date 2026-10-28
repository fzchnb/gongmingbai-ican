from io import BytesIO
from pypdf import PdfReader
from work_source import work_source
from test_projects import client, setup, FIELDS
import main


def test_excerpt_preserves_exact_words_numbers_negation_and_correction_without_paraphrasing():
    original='今天天气真好。今天干了一天，每天350元，借支100元。工资还没收到。谢谢你！'
    correction='借支不是100，是80，其他不变。'
    result=work_source(original,[{'instruction':correction}])
    assert result['has_source']
    assert [f['text'] for f in result['fragments']]==['今天干了一天，每天350元，借支100元。','工资还没收到。']
    assert result['corrections'][0]['fragments'][0]['text']==correction
    assert '还没收到' in result['keywords'] and '80' in result['keywords']
    for f in result['fragments']:
        assert f['text'] in original and ''.join(p['text'] for p in f['parts'])==f['text']


def test_manual_no_source_and_bounded_long_sources_keep_recent_corrections():
    assert not work_source('手动填写')['has_source']
    original='嗯'*300+'今天工资还没收到。'+'啊'*300
    result=work_source(original,[{'instruction':f'借支改为{n}元。'} for n in range(10)])
    assert result['shortened'] and result['corrections_shortened']
    assert [c['number'] for c in result['corrections']]==[8,9,10]
    assert all(f['text'] in original and len(f['text'])<=180 for f in result['fragments'])
    assert '还没收到' in ''.join(f['text'] for f in result['fragments'])


def work_task(c,h,p,body):
    t=c.post('/api/v1/tasks',headers=h,json={'project_id':p,'request_id':main.uid(),**body}).json()
    if t['status']=='queued':main.run_task(main.store.get('', 'tasks',t['id']) or t)
    value=c.get('/api/v1/tasks/'+t['id'],headers=h).json()
    assert value['status']=='completed',value
    return value['result']


def test_excerpt_available_in_draft_recent_ledger_full_source_and_pdf_after_corrections(client,monkeypatch):
    c=client;h,owner,p=setup(c)
    original='先打个招呼。今天干1天，每天350元，借支100元。工资还没收到。谢谢您。'
    monkeypatch.setattr(main.ai,'parse',lambda *args:FIELDS)
    d=work_task(c,h,p,{'type':'work','text':original})
    assert d['source_excerpt']['has_source']
    monkeypatch.setattr(main.ai,'revise',lambda *args:{'changes':{'advance':'80'},'reply':'已按要求修改借支。'})
    d=work_task(c,h,p,{'type':'revise','text':'借支不是100，是80元。','draft_id':d['id'],'expected_revision':0,'fields':FIELDS})
    assert d['source_excerpt']['corrections'][0]['fragments'][0]['text']=='借支不是100，是80元。'
    assert c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json={**d['fields'],'expected_revision':1}).status_code==200
    entry=c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()['entries'][0]
    assert entry['source_excerpt']['has_source'] and len(entry['source_excerpt']['corrections'])==1
    source=c.get('/api/v1/drafts/'+d['id']+'/source',headers=h).json()
    assert source['text']==original and source['excerpt']==entry['source_excerpt']
    response=c.get('/api/v1/projects/'+p+'/archive.pdf',headers=h)
    assert response.status_code==200
    pdf=''.join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages).replace('\n','')
    assert '三、务工证据时间线' in pdf and '记工原话精选' in pdf
    assert '今天干1天，每天350元，借支100元。' in pdf and '工资还没收到。' in pdf
    assert '第1次纠正精选' in pdf and '借支不是100，是80元。' in pdf
    assert '先打个招呼' not in pdf and '谢谢您' not in pdf
    other,_,_=setup(c)
    assert c.get('/api/v1/drafts/'+d['id']+'/source',headers=other).status_code==404


def test_saved_entry_revision_source_includes_latest_correction_without_duplicates(client,monkeypatch):
    c=client;h,owner,p=setup(c)
    monkeypatch.setattr(main.ai,'parse',lambda *args:FIELDS)
    d=work_task(c,h,p,{'type':'work','text':'今天干1天，每天350元，借支100元。'})
    c.post('/api/v1/drafts/'+d['id']+'/confirm',headers=h,json=FIELDS)
    entry=c.get('/api/v1/projects/'+p+'/ledger',headers=h).json()['entries'][0]
    editing=c.post('/api/v1/drafts',headers=h,json={'project_id':p,'entry_id':entry['id'],'expected_entry_version':entry['created_at'],'fields':FIELDS}).json()
    assert editing['source_text']==d['source_text']
    monkeypatch.setattr(main.ai,'revise',lambda *args:{'changes':{'advance':'80'},'reply':'已修改。'})
    changed=work_task(c,h,p,{'type':'revise','text':'借支改成80元。','draft_id':editing['id'],'expected_revision':0,'fields':FIELDS})
    assert c.post('/api/v1/drafts/'+editing['id']+'/confirm',headers=h,json={**changed['fields'],'expected_revision':1}).status_code==200
    source=c.get('/api/v1/drafts/'+d['id']+'/source',headers=h).json()
    assert len(source['corrections'])==1 and source['corrections'][0]['instruction']=='借支改成80元。'
    assert len(source['excerpt']['corrections'])==1
