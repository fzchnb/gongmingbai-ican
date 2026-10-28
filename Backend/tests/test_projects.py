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
    monkeypatch.setattr(main, 'guest_attempts', {})
    return TestClient(main.app)


def setup(client):
    session = client.post('/api/v1/auth/guest').json()
    headers = {'Authorization': 'Bearer ' + session['access_token']}
    project = client.post('/api/v1/projects', headers=headers,
                          json={'name': '删除测试项目', 'boss': '测试师傅'}).json()['id']
    return headers, session['user']['id'], project


FIELDS = {'date': '2026-10-25', 'days': '1', 'day_rate': '350', 'advance': '100'}


def test_deletion_requires_confirmation_and_ownership_and_is_idempotent(client):
    h, owner, project = setup(client)
    other, _, _ = setup(client)
    route = '/api/v1/projects/' + project
    assert client.delete(route, headers=h).status_code == 400
    assert not main.store.get(owner, 'projects', project).get('deleted_at')
    assert client.delete(route + '?confirmed=true', headers=other).status_code == 404
    for _ in range(2):
        assert client.delete(route + '?confirmed=true', headers=h).json() == {'id': project, 'deleted': True}
    assert client.get('/api/v1/projects', headers=h).json() == []
    assert len(client.get('/api/v1/projects', headers=other).json()) == 1


def test_deleted_project_closes_related_reads_and_writes_but_preserves_sources(client):
    h, owner, project = setup(client)
    survivor = client.post('/api/v1/projects', headers=h, json={'name': '保留项目', 'boss': '另一师傅'}).json()['id']
    asset = client.post('/api/v1/assets?project_id=' + project, headers=h,
                        files={'file': ('source.mp3', b'test-audio', 'audio/mpeg')}).json()
    draft = client.post('/api/v1/drafts', headers=h, json={'project_id': project, 'fields': FIELDS}).json()
    assert client.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=FIELDS).status_code == 200
    entry = client.get('/api/v1/projects/' + project + '/ledger', headers=h).json()['entries'][0]
    task = client.post('/api/v1/tasks', headers=h, json={'project_id': project, 'type': 'work',
                       'text': '今天一天350', 'request_id': 'delete-related-access'}).json()
    assert client.delete('/api/v1/projects/' + project + '?confirmed=true', headers=h).status_code == 200
    for suffix in ('ledger', 'timeline', 'statement', 'export'):
        assert client.get('/api/v1/projects/' + project + '/' + suffix, headers=h).status_code == 404
    for route in ('/assets/' + asset['id'], '/assets/' + asset['id'] + '/meta', '/tasks/' + task['id']):
        assert client.get('/api/v1' + route, headers=h).status_code == 404
    assert client.post('/api/v1/tasks/' + task['id'] + '/retry', headers=h).status_code == 404
    assert client.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=FIELDS).status_code == 404
    assert client.patch('/api/v1/entries/' + entry['id'], headers=h, json=FIELDS).status_code == 404
    assert client.post('/api/v1/drafts', headers=h, json={'project_id': project, 'fields': FIELDS}).status_code == 404
    assert client.post('/api/v1/assets?project_id=' + project, headers=h,
                       files={'file': ('more.mp3', b'audio', 'audio/mpeg')}).status_code == 404
    assert [p['id'] for p in client.get('/api/v1/projects', headers=h).json()] == [survivor]
    assert client.get('/api/v1/projects/' + survivor + '/ledger', headers=h).status_code == 200
    assert main.store.get(owner, 'entries', entry['id'])
    assert (main.store.root / asset['path']).read_bytes() == b'test-audio'
    assert main.store.get(owner, 'tasks', task['id'])['status'] == 'failed'


def test_deleted_queued_task_never_calls_model(client, monkeypatch):
    h, owner, project = setup(client)
    task = client.post('/api/v1/tasks', headers=h, json={'project_id': project, 'type': 'work',
                       'text': '今天一天350', 'request_id': 'deleted-before-start'}).json()
    client.delete('/api/v1/projects/' + project + '?confirmed=true', headers=h)
    monkeypatch.setattr(main.ai, 'parse', lambda *_: pytest.fail('Deleted tasks must not call the model'))
    main.run_task(task)  # The worker may already have fetched the queued task.
    assert main.store.list(owner, 'drafts') == []
    saved = main.store.get(owner, 'tasks', task['id'])
    assert saved['status'] == 'failed' and saved['error'] == '项目已删除，本次处理已停止'


@pytest.mark.parametrize('task_type', ['work', 'revise', 'reconcile'])
def test_deletion_during_model_call_cannot_commit_result(client, monkeypatch, task_type):
    h, owner, project = setup(client)
    body = {'project_id': project, 'type': task_type, 'text': '今天一天350', 'request_id': 'delete-during-' + task_type}
    if task_type == 'revise':
        body['fields'] = FIELDS
    if task_type == 'reconcile':
        body['asset_id'] = client.post('/api/v1/assets?project_id=' + project, headers=h,
            files={'file': ('screen.png', b'test-image', 'image/png')}).json()['id']

    def model(*_):
        assert client.delete('/api/v1/projects/' + project + '?confirmed=true', headers=h).status_code == 200
        return {'changes': {'day_rate': '360'}, 'reply': '已修改'} if task_type == 'revise' else FIELDS

    monkeypatch.setattr(main.ai, {'work': 'parse', 'revise': 'revise', 'reconcile': 'vision'}[task_type], model)
    task = client.post('/api/v1/tasks', headers=h, json=body).json()
    main.run_task(task)
    saved = main.store.get(owner, 'tasks', task['id'])
    assert saved['status'] == 'failed' and 'result' not in saved
    assert main.store.list(owner, 'drafts') == []
    assert main.store.list(owner, 'entries') == []


def test_delete_cors_and_capability(client):
    response = client.options('/api/v1/projects/anything', headers={
        'Origin': 'http://127.0.0.1:5173', 'Access-Control-Request-Method': 'DELETE',
        'Access-Control-Request-Headers': 'authorization'})
    assert response.status_code == 200
    assert 'DELETE' in response.headers['access-control-allow-methods']
    assert 'project_delete' in client.get('/health').json()['capabilities']
