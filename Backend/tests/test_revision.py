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


def setup(c):
    token = c.post('/api/v1/auth/guest').json()['access_token']
    headers = {'Authorization': 'Bearer ' + token}
    project = c.post('/api/v1/projects', headers=headers, json={'name': '纠正测试', 'boss': '测试师傅'}).json()['id']
    fields = {'date': '2026-10-24', 'days': '1', 'day_rate': '350', 'overtime_hours': '2',
              'overtime_rate': '30', 'advance': '100'}
    draft = c.post('/api/v1/drafts', headers=headers, json={'project_id': project, 'fields': fields}).json()
    return headers, project, fields, draft


def revision(c, headers, project, draft, fields, request_id, text='借支改80'):
    r = c.post('/api/v1/tasks', headers=headers, json={'type': 'revise', 'project_id': project,
               'draft_id': draft['id'], 'fields': fields, 'expected_revision': draft.get('revision', 0),
               'text': text, 'request_id': request_id})
    assert r.status_code == 200, r.text
    main.run_task(r.json())
    return c.get('/api/v1/tasks/' + r.json()['id'], headers=headers).json()


def test_multi_turn_preserves_manual_edits_and_only_confirms_once(client, monkeypatch):
    c = client
    h, p, fields, draft = setup(c)
    fields['day_rate'] = '360'  # A manual edit made before speaking the correction.
    seen = []
    def revise(current, instruction, today, history, context=None):
        seen.append((current.copy(), len(history)))
        return {'changes': {'advance': '80'} if not history else {'overtime_hours': '3'}, 'reply': '已按你说的修改，请核对。'}
    monkeypatch.setattr(main.ai, 'revise', revise)
    first = revision(c, h, p, draft, fields, 'correction-round-001')['result']
    assert first['fields']['day_rate'] == '360' and first['calculation']['balance_fen'] == 34000
    assert c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()['entries'] == []
    second = revision(c, h, p, first, first['fields'], 'correction-round-002', '加班改3小时')['result']
    assert second['revision'] == 2 and seen[1][1] == 1
    assert second['calculation']['balance_fen'] == 37000
    stale = {**second['fields'], 'expected_revision': 0}
    assert c.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=stale).status_code == 409
    body = {**second['fields'], 'expected_revision': 2}
    for _ in range(2):
        assert c.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=body).status_code == 200
    ledger = c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()
    assert ledger['totals'] == {'wage_fen': 45000, 'advance_fen': 8000, 'balance_fen': 37000}
    assert len(ledger['entries']) == 1 and len(ledger['entries'][0]['revision_history']) == 2


def test_revision_checks_owner_project_and_confirmed_state(client):
    c = client
    h, p, fields, draft = setup(c)
    other, _, _, _ = setup(c)
    body = {'type': 'revise', 'project_id': p, 'draft_id': draft['id'], 'text': '借支80', 'request_id': 'ownership-revision-001'}
    assert c.post('/api/v1/tasks', headers=other, json=body).status_code == 404
    second = c.post('/api/v1/projects', headers=h, json={'name': '另一项目', 'boss': '另一师傅'}).json()['id']
    assert c.post('/api/v1/tasks', headers=h, json={**body, 'project_id': second}).status_code == 400
    c.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=fields)
    assert c.post('/api/v1/tasks', headers=h, json=body).status_code == 409


def test_queued_revision_cannot_overwrite_confirmed_draft(client, monkeypatch):
    c = client
    h, p, fields, draft = setup(c)
    row = c.post('/api/v1/tasks', headers=h, json={'type': 'revise', 'project_id': p,
        'draft_id': draft['id'], 'text': '借支改80', 'request_id': 'confirmed-while-queued'}).json()
    c.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=fields)
    def unexpected(*args):
        pytest.fail('A confirmed draft should be rejected before calling the model')
    monkeypatch.setattr(main.ai, 'revise', unexpected)
    main.run_task(row)
    assert c.get('/api/v1/tasks/' + row['id'], headers=h).json()['status'] == 'failed'
    assert c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()['totals']['balance_fen'] == 31000


def test_voice_revision_and_missing_rate_still_requires_confirmation(client, monkeypatch):
    c = client
    h, p, fields, draft = setup(c)
    asset = c.post('/api/v1/assets?project_id=' + p, headers=h,
                   files={'file': ('correction.mp3', b'synthetic-audio', 'audio/mpeg')}).json()
    monkeypatch.setattr(main.ai, 'transcribe', lambda *_: '加班单价还没有说好')
    def revise(current, instruction, *_):
        assert instruction == '加班单价还没有说好'
        return {'changes': {'overtime_rate': None}, 'reply': '加班每小时是多少元？'}
    monkeypatch.setattr(main.ai, 'revise', revise)
    row = c.post('/api/v1/tasks', headers=h, json={'type': 'revise', 'project_id': p, 'draft_id': draft['id'],
                 'asset_id': asset['id'], 'request_id': 'voice-correction-001'}).json()
    main.run_task(row)
    value = c.get('/api/v1/tasks/' + row['id'], headers=h).json()['result']
    assert value['revisions'][0]['asset_id'] == asset['id']
    assert value['calculation']['missing'] == ['加班单价']
    assert c.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=value['fields']).status_code == 422
    assert c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()['entries'] == []


def test_partial_preview_reports_missing_instead_of_guessing(client):
    h, _, _, _ = setup(client)
    r = client.post('/api/v1/drafts/preview', headers=h, json={'days': None, 'date': None, 'day_rate': None})
    assert r.status_code == 200
    assert r.json()['missing'] == ['日期', '天数', '日单价']


def saved_entry(c):
    h, p, fields, draft = setup(c)
    assert c.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=fields).status_code == 200
    entry = c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()['entries'][0]
    return h, p, fields, entry


def edit_draft(c, h, p, fields, entry):
    response = c.post('/api/v1/drafts', headers=h, json={'project_id': p, 'entry_id': entry['id'],
                      'expected_entry_version': entry.get('updated_at') or entry['created_at'], 'fields': fields})
    assert response.status_code == 200, response.text
    return response.json()


def test_saved_entry_ai_correction_updates_same_entry_only_after_confirmation(client, monkeypatch):
    c = client
    h, p, fields, entry = saved_entry(c)
    fields['note'] = '一层吊顶\n材料已经送到，明天继续安装。'
    draft = edit_draft(c, h, p, fields, entry)
    monkeypatch.setattr(main.ai, 'revise', lambda *_: {'changes': {'advance': '80'}, 'reply': '借支改为80元，其他保持不变。'})
    result = revision(c, h, p, draft, fields, 'saved-entry-correction-01')['result']
    assert result['source_entry_id'] == entry['id']
    unchanged = c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()
    assert len(unchanged['entries']) == 1 and unchanged['totals']['balance_fen'] == 31000
    for _ in range(2):
        response = c.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h,
                          json={**result['fields'], 'expected_revision': 1})
        assert response.status_code == 200, response.text
    ledger = c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()
    assert len(ledger['entries']) == 1 and ledger['entries'][0]['id'] == entry['id']
    assert ledger['totals'] == {'wage_fen': 41000, 'advance_fen': 8000, 'balance_fen': 33000}
    assert ledger['entries'][0]['fields']['note'] == fields['note']
    assert len(ledger['entries'][0]['revision_history']) == 1
    events = c.get('/api/v1/projects/' + p + '/timeline', headers=h).json()
    edits = [event for event in events if 'before' in event]
    assert len(edits) == 1 and edits[0]['before']['fields']['advance'] == '100'
    assert edits[0]['after']['fields']['advance'] == '80'


def test_edit_draft_owner_project_and_stale_snapshot_checks(client):
    c = client
    h, p, fields, entry = saved_entry(c)
    other, _, _, _ = setup(c)
    body = {'project_id': p, 'entry_id': entry['id'], 'fields': fields}
    assert c.post('/api/v1/drafts', headers=other, json=body).status_code == 404
    other_project = c.post('/api/v1/projects', headers=h, json={'name': '其他工地', 'boss': '另一师傅'}).json()['id']
    assert c.post('/api/v1/drafts', headers=h, json={**body, 'project_id': other_project}).status_code == 400
    c.patch('/api/v1/entries/' + entry['id'], headers=h, json={**fields, 'day_rate': '360'})
    assert c.post('/api/v1/drafts', headers=h,
                  json={**body, 'expected_entry_version': entry['created_at']}).status_code == 409
    assert c.patch('/api/v1/entries/' + entry['id'], headers=h,
                   json={**fields, 'expected_entry_version': entry['created_at']}).status_code == 409


def test_queued_saved_entry_revision_rejects_external_edit_before_model(client, monkeypatch):
    c = client
    h, p, fields, entry = saved_entry(c)
    draft = edit_draft(c, h, p, fields, entry)
    response = c.post('/api/v1/tasks', headers=h, json={'project_id': p, 'type': 'revise',
        'draft_id': draft['id'], 'text': '借支80', 'request_id': 'queued-saved-entry-edit'})
    assert response.status_code == 200
    c.patch('/api/v1/entries/' + entry['id'], headers=h, json={**fields, 'day_rate': '360'})
    def unexpected(*_):
        pytest.fail('A stale saved-entry draft must be rejected before model invocation')
    monkeypatch.setattr(main.ai, 'revise', unexpected)
    main.run_task(response.json())
    assert c.get('/api/v1/tasks/' + response.json()['id'], headers=h).json()['status'] == 'failed'
    assert c.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=fields).status_code == 409
    ledger = c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()
    assert len(ledger['entries']) == 1 and ledger['totals']['wage_fen'] == 42000


def test_saved_entry_accepts_voice_correction_and_keeps_audio_reference(client, monkeypatch):
    c = client
    h, p, fields, entry = saved_entry(c)
    draft = edit_draft(c, h, p, fields, entry)
    asset = c.post('/api/v1/assets?project_id=' + p, headers=h,
                   files={'file': ('saved-edit.mp3', b'voice-test-fixture', 'audio/mpeg')}).json()
    monkeypatch.setattr(main.ai, 'transcribe', lambda *_: '借支改八十，备注今天做了吊顶')
    def revise(current, instruction, *_):
        assert current['day_rate'] == '350' and '吊顶' in instruction
        return {'changes': {'advance': '80', 'note': '今天做了吊顶'}, 'reply': '已修改，请核对。'}
    monkeypatch.setattr(main.ai, 'revise', revise)
    response = c.post('/api/v1/tasks', headers=h, json={'project_id': p, 'type': 'revise',
        'draft_id': draft['id'], 'asset_id': asset['id'], 'request_id': 'saved-entry-voice-edit'})
    assert response.status_code == 200
    main.run_task(response.json())
    result = c.get('/api/v1/tasks/' + response.json()['id'], headers=h).json()['result']
    assert result['revisions'][0]['asset_id'] == asset['id']
    assert c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()['totals']['balance_fen'] == 31000
    assert c.post('/api/v1/drafts/' + draft['id'] + '/confirm', headers=h, json=result['fields']).status_code == 200
    ledger = c.get('/api/v1/projects/' + p + '/ledger', headers=h).json()
    assert len(ledger['entries']) == 1 and ledger['entries'][0]['fields']['note'] == '今天做了吊顶'
    assert ledger['totals']['balance_fen'] == 33000
