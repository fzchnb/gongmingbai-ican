import io
import json
import zipfile
from test_projects import client, setup, FIELDS
import main


def test_ai_voice_and_corrections_are_not_materials_but_screenshot_remains(client, monkeypatch):
    h, owner, project=setup(client)
    voice=client.post('/api/v1/assets?project_id='+project,headers=h,
        files={'file':('instruction.mp3',b'ai-voice','audio/mpeg')}).json()
    assert voice['purpose']=='ai_input'
    assert client.get('/api/v1/projects/'+project+'/timeline',headers=h).json()==[]
    monkeypatch.setattr(main.ai,'transcribe',lambda *_:'今天一天350，借支100')
    monkeypatch.setattr(main.ai,'parse',lambda *_:FIELDS)
    task=client.post('/api/v1/tasks',headers=h,json={'type':'work','project_id':project,
        'asset_id':voice['id'],'request_id':'ai-voice-not-evidence'}).json()
    main.run_task(task)
    draft=client.get('/api/v1/tasks/'+task['id'],headers=h).json()['result']
    assert client.post('/api/v1/drafts/'+draft['id']+'/confirm',headers=h,json=FIELDS).status_code==200
    screenshot=client.post('/api/v1/assets?project_id='+project+'&purpose=evidence',headers=h,
        files={'file':('screen.png',b'screenshot','image/png')}).json()
    events=client.get('/api/v1/projects/'+project+'/timeline',headers=h).json()
    assert len(events)==2
    assert {e.get('asset_id') for e in events}=={None,screenshot['id']}
    package=client.get('/api/v1/projects/'+project+'/export',headers=h)
    with zipfile.ZipFile(io.BytesIO(package.content)) as z:
        manifest=json.loads(z.read('manifest.json'))
        assert [a['id'] for a in manifest]==[screenshot['id']]
        assert z.read(manifest[0]['archive_path'])==b'screenshot'
        assert not any(voice['id'] in name for name in z.namelist())
    assert client.get('/api/v1/drafts/'+draft['id']+'/source',headers=h).json()['text']=='今天一天350，借支100'


def test_legacy_ai_audio_is_hidden_without_deleting_source_or_changing_explicit_evidence(client):
    h,owner,project=setup(client)
    voice=client.post('/api/v1/assets?project_id='+project,headers=h,
        files={'file':('old.mp3',b'old-voice','audio/mpeg')}).json()
    voice.pop('purpose')
    main.store.put(owner,'assets',voice)
    main.store.put(owner,'events',main.item(project_id=project,title='原始资料已上传',asset_id=voice['id']))
    main.store.put(owner,'events',main.item(project_id=project,title='记工已由我核对',asset_id=voice['id']))
    events=client.get('/api/v1/projects/'+project+'/timeline',headers=h).json()
    assert len(events)==1 and 'asset_id' not in events[0]
    assert main.store.get(owner,'assets',voice['id'])
    with zipfile.ZipFile(io.BytesIO(client.get('/api/v1/projects/'+project+'/export',headers=h).content)) as z:
        assert json.loads(z.read('manifest.json'))==[]
    evidence=client.post('/api/v1/assets?project_id='+project+'&purpose=evidence',headers=h,
        files={'file':('saved-recording.mp3',b'old-voice','audio/mpeg')}).json()
    assert evidence['id']!=voice['id'] and evidence['purpose']=='evidence'
