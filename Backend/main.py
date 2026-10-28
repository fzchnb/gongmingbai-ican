import base64
import csv
import hashlib
import mimetypes
import hmac
import io
import json
import os
import secrets
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import date as Date, datetime, timezone, timedelta
from typing import Literal

import httpx
from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import quote
from archive_pdf import render_archive
from work_source import work_source
load_dotenv(Path(__file__).parent / '.env')
from store import Store
from domain import calculate, compare, cents
import ai
import agent
from workflows import Reconciliation

store = Store()
production = os.getenv('APP_ENV') == 'production'
if production and not (store.cloud and os.getenv('SUPABASE_PUBLISHABLE_KEY')):
    raise RuntimeError('生产模式必须配置Supabase，禁止使用本地游客身份')
secret_path = store.root / '.session_secret'
if not secret_path.exists():
    secret_path.write_text(secrets.token_hex(32))
local_secret = secret_path.read_text().encode()
stopping = threading.Event()
work_available = threading.Event()
guest_attempts = {}
guest_lock = threading.Lock()


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def item(**fields):
    return {'id': uid(), 'created_at': now(), **fields}


def owned(owner, kind, identifier):
    row = store.get(owner, kind, identifier)
    if not row or row.get('deleted_at'):
        raise HTTPException(404, '记录不存在')
    if row.get('project_id'):
        project = store.get(owner, 'projects', row['project_id'])
        if not project or project.get('deleted_at'):
            raise HTTPException(404, '项目不存在或已删除')
    return row


def entry_version(entry):
    return entry.get('updated_at') or entry['created_at']


def current_edit_entry(owner, draft):
    entry = owned(owner, 'entries', draft['source_entry_id'])
    if entry_version(entry) != draft['expected_entry_version']:
        raise ValueError('这笔记工已在别处修改，请返回账本重新打开后再修改')
    return entry


def identity(authorization: str = Header(default='')):
    token = authorization.removeprefix('Bearer ')
    if store.cloud:
        r = store.client.get(store.url + '/auth/v1/user', headers={'apikey': os.getenv('SUPABASE_PUBLISHABLE_KEY', ''),
                     'Authorization': 'Bearer ' + token}, timeout=15)
        if r.status_code != 200:
            raise HTTPException(401, '会话已失效，请重新进入')
        return r.json()['id']
    try:
        with store.db() as db:
            if db.execute('SELECT 1 FROM revoked_tokens WHERE digest=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone():
                raise ValueError()
        parts = token.split('.')
        if len(parts) not in (3, 4):
            raise ValueError()
        owner, expiry, signature = parts[0], parts[1], parts[-1]
        message = '.'.join(parts[:-1]).encode()
        if not hmac.compare_digest(hmac.new(local_secret, message, 'sha256').hexdigest(), signature) or int(expiry) < time.time():
            raise ValueError()
        uuid.UUID(owner)
        return owner
    except (ValueError, TypeError):
        raise HTTPException(401, '请先创建游客会话')


def asset_bytes(owner, identifier):
    row = owned(owner, 'assets', identifier)
    if store.cloud:
        r = httpx.get(store.url + '/storage/v1/object/evidence/' + row['path'], headers={
            'apikey': store.key, 'Authorization': 'Bearer ' + store.key}, timeout=30)
        r.raise_for_status()
        return row, r.content
    return row, (store.root / row['path']).read_bytes()


def presented_draft(owner, draft):
    history=draft.get('revisions',[])
    if draft.get('source_entry_id'):
        previous=owned(owner,'entries',draft['source_entry_id']).get('revision_history',[])
        history=previous if draft.get('confirmed') else previous+history
    return {**draft,'source_excerpt':work_source(draft.get('source_text',''),history)}


def task_stage(task, label, **values):
    with store.lock:
        owned(task['owner_id'], 'projects', task['project_id'])
        task.update(stage=label, **values)
        store.put(task['owner_id'], 'tasks', task)


def run_task(task):
    owner = task['owner_id']
    try:
        with store.lock:
            owned(owner, 'projects', task['project_id'])
            task.update(status='running', stage='正在读取项目账本…', started_at=now())
            task['context'] = agent.context(store, owner, task['project_id'])
            store.put(owner, 'tasks', task)
        if task['type'] in ('work', 'revise'):
            text = task.get('text', '')
            if task.get('asset_id'):
                asset, data = asset_bytes(owner, task['asset_id'])
                task_stage(task, '正在把录音转成文字…')
                text = ai.transcribe(data, asset['mime'])
                task_stage(task, '正在按要求修改草稿…' if task['type']=='revise' else '正在整理记工草稿…', transcript=text)
            else:
                task_stage(task, '正在按要求修改草稿…' if task['type']=='revise' else '正在整理记工草稿…')
            today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
            if task['type'] == 'revise':
                source = owned(owner, 'drafts', task['draft_id']) if task.get('draft_id') else None
                if source and (source['confirmed'] or source.get('revision', 0) != task['expected_revision']):
                    raise ValueError('草稿已保存或更新，请返回重新核对后再修改')
                if source and source.get('source_entry_id'):
                    current_edit_entry(owner, source)
                before = task.get('fields') or (source or {}).get('fields', {})
                update = ai.revise(before, text, today, (source or {}).get('revisions', []), task['context'])
                value = normalize_work({**before, **update['changes']})
                with store.lock:
                    owned(owner, 'projects', task['project_id'])
                    if source:
                        current = owned(owner, 'drafts', source['id'])
                        if current['confirmed'] or current.get('revision', 0) != task['expected_revision']:
                            raise ValueError('草稿已保存或更新，请返回重新核对后再修改')
                        if current.get('source_entry_id'):
                            current_edit_entry(owner, current)
                        draft = current
                    else:
                        draft = item(project_id=task['project_id'], source_text='', asset_id=None,
                                     confirmed=False, revision=0)
                    history = draft.get('revisions', []) + [{'instruction': text, 'reply': update['reply'],
                                'before': before, 'after': value, 'asset_id': task.get('asset_id'), 'created_at': now()}]
                    draft.update(fields=value, calculation=calculate(value), revisions=history,
                                 revision=draft.get('revision', 0) + 1, assistant_message=update['reply'])
                    store.put(owner, 'drafts', draft)
            else:
                value = normalize_work(ai.parse(text, today, task['context']))
                calculation = calculate(value)
                message = '请再告诉我：' + '、'.join(calculation['missing']) if calculation['missing'] else '已整理好，核对后就能保存。'
                draft = item(project_id=task['project_id'], source_text=text, asset_id=task.get('asset_id'),
                             fields=value, calculation=calculation, confirmed=False, revision=0,
                             revisions=[], assistant_message=message)
                with store.lock:
                    owned(owner, 'projects', task['project_id'])
                    store.put(owner, 'drafts', draft)
            task['result'] = presented_draft(owner,draft)
        else:
            asset, data = asset_bytes(owner, task['asset_id'])
            task_stage(task, '正在识别截图并结合账本核对…')
            extracted = ai.vision(data, asset['mime'], task['context'])
            task['result'] = {'extracted': extracted, 'asset_id': asset['id'], 'project_id': task['project_id'],
                              'context_summary': {'project': task['context']['project'], 'totals': task['context']['totals'],
                              'dates': list(task['context']['day_totals']), 'ledger_version': task['context']['ledger_version']}}
        with store.lock:
            owned(owner, 'projects', task['project_id'])
            task.update(status='completed', stage='请核对识别结果', finished_at=now())
            store.put(owner, 'tasks', task)
    except Exception as exc:
        # Never echo provider headers, response bodies, or secrets to the client.
        message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else '服务处理失败，请检查网络或模型配置后重试'
        with store.lock:
            project = store.get(owner, 'projects', task['project_id'])
            deleted = not project or bool(project.get('deleted_at'))
            if deleted:
                message = '项目已删除，本次处理已停止'
                task.pop('result', None)
            task.update(status='failed', stage='项目已删除' if deleted else '需要重试',
                        error=message[:300], finished_at=now())
            store.put(owner, 'tasks', task)


def worker():
    while not stopping.is_set():
        work_available.clear()
        try:
            for task in store.all_tasks():
                if stopping.is_set():
                    return
                if task['status'] == 'queued':
                    run_task(task)
        except Exception:
            pass  # Storage outage: keep persisted work and try the next poll.
        work_available.wait(30)


@asynccontextmanager
async def lifespan(app):
    for task in store.all_tasks():
        if task['status'] == 'running':
            task.update(status='failed', error='服务重启中断了处理，请重试')
            store.put(task['owner_id'], 'tasks', task)
    stopping.clear()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    yield
    stopping.set()
    work_available.set()
    thread.join(timeout=2)


app = FastAPI(title='工明白 API', version='0.1.0', lifespan=lifespan)

@app.exception_handler(httpx.RequestError)
@app.exception_handler(httpx.HTTPStatusError)
async def upstream_error(request, exc):
    return JSONResponse(status_code=503, content={'detail': '云端服务暂时无法连接，请稍后重试'})
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','),
                   allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Authorization', 'Content-Type'],
                   expose_headers=['Content-Disposition'])
P = '/api/v1'
from accounts import build_router
app.include_router(build_router(lambda: store, identity, local_secret))


@app.get('/health')
def health():
    return {'ok': True, 'mode': 'cloud' if store.cloud else 'local-development', 'ai_configured': bool(os.getenv('DASHSCOPE_API_KEY')),
            'guest_enabled': not store.cloud or os.getenv('ENABLE_GUEST', 'false').lower() == 'true',
            'capabilities': ['draft_revision', 'entry_revision', 'project_delete', 'material_sources', 'material_purposes', 'project_agent_workflow', 'work_settlement', 'voice_progress', 'reconciliation_followup', 'evidence_pdf', 'work_source_excerpt', 'receipt_date_prefill']}


@app.post(P + '/auth/guest')
def guest(request: Request):
    address = request.client.host if request.client else 'unknown'
    with guest_lock:
        threshold = time.time() - 3600
        for ip in list(guest_attempts):
            guest_attempts[ip] = [stamp for stamp in guest_attempts[ip] if stamp > threshold]
            if not guest_attempts[ip]:
                del guest_attempts[ip]
        attempts = guest_attempts.setdefault(address, [])
        if len(attempts) >= int(os.getenv('MAX_GUEST_PER_HOUR', '60')):
            raise HTTPException(429, '游客创建过于频繁，请稍后再试')
        attempts.append(time.time())
    if store.cloud:
        r = httpx.post(store.url + '/auth/v1/signup', headers={'apikey': os.getenv('SUPABASE_PUBLISHABLE_KEY', '')}, json={}, timeout=20)
        if r.status_code >= 400:
            raise HTTPException(503, '游客登录失败，请检查Supabase匿名登录配置')
        return r.json()
    owner, expiry = uid(), str(int(time.time()) + 86400 * 30)
    message = owner + '.' + expiry
    return {'access_token': message + '.' + hmac.new(local_secret, message.encode(), 'sha256').hexdigest(),
            'user': {'id': owner}, 'mode': 'local-development'}


class Refresh(BaseModel):
    refresh_token: str


@app.post(P + '/auth/refresh')
def refresh(body: Refresh):
    if not store.cloud:
        raise HTTPException(400, '本地模式无需刷新')
    r = httpx.post(store.url + '/auth/v1/token?grant_type=refresh_token', headers={
        'apikey': os.getenv('SUPABASE_PUBLISHABLE_KEY', '')}, json=body.model_dump(), timeout=20)
    if r.status_code >= 400:
        raise HTTPException(401, '会话无法刷新，请重新进入')
    return r.json()


class Project(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    boss: str = Field(min_length=1, max_length=80)


@app.get(P + '/projects')
def projects(owner=Depends(identity)):
    return [row for row in store.list(owner, 'projects') if not row.get('deleted_at')]


@app.post(P + '/projects')
def create_project(body: Project, owner=Depends(identity)):
    return store.put(owner, 'projects', item(**body.model_dump()))


@app.delete(P + '/projects/{project_id}')
def delete_project(project_id: str, confirmed: bool = False, owner=Depends(identity)):
    with store.lock:
        project = store.get(owner, 'projects', project_id)
        if not project:
            raise HTTPException(404, '项目不存在')
        if not confirmed:
            raise HTTPException(400, '请先确认删除项目')
        if not project.get('deleted_at'):
            project['deleted_at'] = now()
            rows = [('projects', project)]
            for task in store.list(owner, 'tasks'):
                if task['project_id'] == project_id and task['status'] in ('queued', 'running'):
                    task.update(status='failed', stage='项目已删除', error='项目已删除，本次处理已停止', finished_at=now())
                    task.pop('result', None)
                    rows.append(('tasks', task))
            # Retain source records; the parent tombstone closes every related API.
            store.batch(owner, rows)
    return {'id': project_id, 'deleted': True}


def totals(owner, project_id, day=None):
    entries = [r for r in store.list(owner, 'entries') if r['project_id'] == project_id and (not day or r['date'] == day)]
    payments = [r for r in store.list(owner, 'payments') if r['project_id'] == project_id and (not day or r['date'] == day)]
    wage = sum(r['wage_fen'] for r in entries)
    advance = sum(r['amount_fen'] for r in payments)
    return {'wage_fen': wage, 'advance_fen': advance, 'balance_fen': wage - advance}


@app.get(P + '/projects/{project_id}/ledger')
def ledger(project_id: str, owner=Depends(identity)):
    owned(owner, 'projects', project_id)
    return {'totals': totals(owner, project_id), 'entries': [{**r,'source_excerpt':work_source(r.get('source_text',''),r.get('revision_history',[]))} for r in store.list(owner, 'entries') if r['project_id'] == project_id],
            'payments': [r for r in store.list(owner, 'payments') if r['project_id'] == project_id and r['amount_fen']>0]}


@app.post(P + '/assets')
def upload(project_id: str, file: UploadFile = File(...), purpose: Literal['evidence', 'ai_input', 'reconcile'] | None = None, owner=Depends(identity)):
    owned(owner, 'projects', project_id)
    data = file.file.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, '文件必须小于10MB且不能为空')
    mime = (file.content_type or '').split(';')[0]
    if mime in ('application/octet-stream', ''):
        mime = mimetypes.guess_type(file.filename or '')[0] or mime
    if mime not in ('image/jpeg', 'image/png', 'image/webp', 'audio/mp3', 'audio/mpeg', 'audio/wav', 'audio/aac', 'audio/mp4'):
        raise HTTPException(400, '请选择图片或录音文件')
    digest = hashlib.sha256(data).hexdigest()
    purpose = purpose or ('ai_input' if mime.startswith('audio/') else 'evidence')
    existing = next((a for a in store.list(owner, 'assets') if a['sha256'] == digest and a['project_id'] == project_id
                     and (a.get('purpose', 'ai_input' if a['mime'].startswith('audio/') else 'evidence') == purpose
                          or {a.get('purpose', 'ai_input' if a['mime'].startswith('audio/') else 'evidence'), purpose} <= {'evidence', 'reconcile'})), None)
    if existing:
        return existing
    row = item(project_id=project_id, mime=mime, name=(file.filename or '资料')[:100], sha256=digest, purpose=purpose, archival_status='staged' if purpose=='reconcile' else 'archived')
    row['path'] = owner + '/' + row['id']
    if store.cloud:
        r = httpx.post(store.url + '/storage/v1/object/evidence/' + row['path'], headers={
            'apikey': store.key, 'Authorization': 'Bearer ' + store.key, 'Content-Type': mime}, content=data, timeout=40)
        r.raise_for_status()
    else:
        path = store.root / row['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    rows = [('assets', row)]
    if purpose == 'evidence':
        rows.append(('events', item(project_id=project_id, title='原始资料已上传', asset_id=row['id'])))
    store.batch(owner, rows)
    return row


@app.get(P + '/assets/{asset_id}')
def download(asset_id: str, owner=Depends(identity)):
    row, data = asset_bytes(owner, asset_id)
    return Response(data, media_type=row['mime'], headers={'Cache-Control': 'no-store'})


@app.get(P + '/assets/{asset_id}/meta')
def asset_meta(asset_id: str, owner=Depends(identity)):
    return owned(owner, 'assets', asset_id)


def is_evidence(asset):
    # Older app versions only uploaded audio for AI dictation/corrections.
    purpose = asset.get('purpose', 'ai_input' if asset['mime'].startswith('audio/') else 'evidence')
    return purpose == 'evidence' or (purpose == 'reconcile' and asset.get('archival_status') == 'archived')


@app.get(P + '/drafts/{draft_id}/source')
def draft_source(draft_id: str, owner=Depends(identity)):
    draft = owned(owner, 'drafts', draft_id)
    entries=[e for e in store.list(owner,'entries') if e['project_id']==draft['project_id'] and
             (e.get('draft_id')==draft_id or e['id']==draft.get('source_entry_id'))]
    text=entries[0].get('source_text','') if entries else draft.get('source_text','')
    history=entries[0].get('revision_history',[]) if entries else draft.get('revisions',[])
    return {'text':text,'excerpt':work_source(text,history),
            'corrections':[{'instruction':r.get('instruction',''),'reply':r.get('reply',''),'asset_id':r.get('asset_id')} for r in history]}


class WorkFields(BaseModel):
    date: Date | None = None
    days: str | None = None
    day_rate: str | None = None
    overtime_hours: str | None = '0'
    overtime_rate: str | None = None
    advance: str | None = '0'
    received: str | None = '0'
    settled: bool = False
    received_date: Date | None = None
    note: str = Field(default='', max_length=1000)


def normalize_work(value):
    if not isinstance(value, dict):
        raise ValueError('记工信息格式无效，请重试')
    data = {k: (v if k == 'settled' else None if v in (None, '') and k != 'note' else str(v or '') if k == 'note' else str(v))
            for k, v in value.items() if k in WorkFields.model_fields}
    try:
        fields = WorkFields(**data).model_dump(mode='json')
        calculate(fields)
    except ValueError:
        raise ValueError('记工日期或数字无效，请重新核对')
    return fields


class Task(BaseModel):
    project_id: str
    type: Literal['work', 'reconcile', 'revise']
    text: str = Field(default='', max_length=6000)
    asset_id: str | None = None
    request_id: str = Field(min_length=8, max_length=100)
    draft_id: str | None = None
    fields: WorkFields | None = None
    expected_revision: int | None = Field(default=None, ge=0)


@app.post(P + '/tasks')
def create_task(body: Task, owner=Depends(identity)):
    owned(owner, 'projects', body.project_id)
    tasks = store.list(owner, 'tasks')
    previous = next((t for t in tasks if t['request_id'] == body.request_id), None)
    if previous:
        return previous
    if body.type == 'revise':
        if body.draft_id:
            draft = owned(owner, 'drafts', body.draft_id)
            if draft['project_id'] != body.project_id:
                raise HTTPException(400, '草稿所属项目不同')
            if draft['confirmed']:
                raise HTTPException(409, '这笔记工已保存，请在账本中修改')
            if draft.get('source_entry_id'):
                try:
                    current_edit_entry(owner, draft)
                except ValueError as exc:
                    raise HTTPException(409, str(exc))
            if body.expected_revision is not None and body.expected_revision != draft.get('revision', 0):
                raise HTTPException(409, '草稿已更新，请重新核对')
            body.expected_revision = draft.get('revision', 0)
        elif body.fields is None:
            raise HTTPException(422, '请提供需要修改的草稿')
        if body.fields is not None:
            try:
                normalize_work(body.fields.model_dump(mode='json'))
            except ValueError as exc:
                raise HTTPException(422, str(exc))
    if body.asset_id:
        asset = owned(owner, 'assets', body.asset_id)
        if asset['project_id'] != body.project_id:
            raise HTTPException(400, '资料所属项目不同')
    if not body.text.strip() and not body.asset_id:
        raise HTTPException(400, '请先输入文字或上传资料')
    if body.type == 'reconcile' and not body.asset_id:
        raise HTTPException(400, '核账需要截图')
    if body.type == 'reconcile':
        existing_report = next((r for r in store.list(owner, 'reports') if r['project_id'] == body.project_id
                                and r['asset_id'] == body.asset_id), None)
        if existing_report:
            return store.put(owner, 'tasks', item(**body.model_dump(mode='json'), owner_id=owner,
                status='completed', stage='已找到这张截图的核账记录', reused=True, finished_at=now(),
                result={'existing_report':reconciliation.present(owner,existing_report), 'asset_id':body.asset_id,
                        'project_id':body.project_id,'extracted':{}}))
    if len([t for t in tasks if not t.get('reused') and t['created_at'][:10] == now()[:10]]) >= 50:
        raise HTTPException(429, '今天的AI处理额度已用完')
    row = store.put(owner, 'tasks', item(**body.model_dump(mode='json'), owner_id=owner, status='queued', stage='等待处理'))
    work_available.set()
    return row


@app.get(P + '/tasks/{task_id}')
def task_status(task_id: str, owner=Depends(identity)):
    task = owned(owner, 'tasks', task_id)
    if task['status'] == 'completed' and task['type'] in ('work', 'revise'):
        draft = store.get(owner, 'drafts', task.get('result', {}).get('id', ''))
        if draft:
            task['result'] = presented_draft(owner,draft)
    return task


@app.post(P + '/tasks/{task_id}/retry')
def retry_task(task_id: str, owner=Depends(identity)):
    task = owned(owner, 'tasks', task_id)
    if task['status'] != 'failed':
        raise HTTPException(409, '仅失败任务可以重试')
    if task.get('retries', 0) >= 3:
        raise HTTPException(429, '本任务重试次数已用完，请检查配置后重新提交')
    task['retries'] = task.get('retries', 0) + 1
    task.update(status='queued', stage='等待重试', error=None)
    store.put(owner, 'tasks', task)
    work_available.set()
    return task


class Work(BaseModel):
    date: Date
    days: str = '1'
    day_rate: str | None = None
    overtime_hours: str = '0'
    overtime_rate: str | None = None
    advance: str = '0'
    received: str = '0'
    settled: bool = False
    received_date: Date | None = None
    note: str = Field(default='', max_length=1000)
    expected_revision: int | None = Field(default=None, ge=0, exclude=True)
    expected_entry_version: str | None = Field(default=None, max_length=64, exclude=True)


class Manual(BaseModel):
    project_id: str
    fields: WorkFields
    entry_id: str | None = None
    expected_entry_version: str | None = Field(default=None, max_length=64)


def work_fields(body, source=None):
    fields = body.model_dump(mode='json')
    for key in ('received', 'settled', 'received_date'):
        if key not in body.model_fields_set and source and key in source:
            fields[key] = source[key]
    return fields


@app.post(P + '/drafts/preview')
def preview(body: WorkFields, owner=Depends(identity)):
    try:
        return calculate(body.model_dump(mode='json'))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post(P + '/drafts')
def manual(body: Manual, owner=Depends(identity)):
    owned(owner, 'projects', body.project_id)
    entry = None
    if body.entry_id:
        entry = owned(owner, 'entries', body.entry_id)
        if entry['project_id'] != body.project_id:
            raise HTTPException(400, '记工所属项目不同')
        if body.expected_entry_version is not None and body.expected_entry_version != entry_version(entry):
            raise HTTPException(409, '这笔记工已更新，请返回账本重新打开')
    fields = work_fields(body.fields, entry.get('fields') if entry else None)
    try:
        calculation = calculate(fields)
    except ValueError as e:
        raise HTTPException(422, str(e))
    draft=store.put(owner, 'drafts', item(project_id=body.project_id, fields=fields, calculation=calculation,
                        confirmed=False, source_text=entry.get('source_text','') if entry else '手动填写', asset_id=None,
                        revision=0, revisions=[], **({'source_entry_id': entry['id'],
                        'expected_entry_version': entry_version(entry)} if entry else {})))
    return presented_draft(owner,draft)


def work_payment_rows(owner, entry, fields, calculation):
    rows = []
    for name, amount, day in (
        ('advance', calculation['advance_fen'], fields['date']),
        ('received', calculation['received_fen'], fields.get('received_date') or fields['date'])
    ):
        payment_id = str(uuid.uuid5(uuid.UUID(entry['draft_id']), name))
        previous = store.get(owner, 'payments', payment_id)
        # Updating a work entry only adjusts its own derived payments, never screenshot/manual receipts.
        if amount or previous:
            rows.append(('payments', {'id': payment_id, 'created_at': (previous or {}).get('created_at', now()),
                'project_id': entry['project_id'], 'entry_id': entry['id'], 'draft_id': entry['draft_id'],
                'date': day, 'amount_fen': amount, 'type': name}))
    return rows


def entry_update_rows(owner, entry, fields, calculation, draft=None):
    before = json.loads(json.dumps(entry))
    updated = {**entry, 'fields': fields, 'date': fields['date'],
               'wage_fen': calculation['wage_fen'], 'updated_at': now()}
    if draft:
        updated['revision_history'] = entry.get('revision_history', []) + draft.get('revisions', [])
    event = item(project_id=entry['project_id'], title='记工已修改 · 历史已保留', before=before, after=updated)
    if draft:
        event.update(id=str(uuid.uuid5(uuid.UUID(draft['id']), 'edit-event')), draft_id=draft['id'])
    rows = [('entries', updated), *work_payment_rows(owner, entry, fields, calculation), ('events', event)]
    return updated, rows


@app.post(P + '/drafts/{draft_id}/confirm')
def confirm(draft_id: str, body: Work, owner=Depends(identity)):
    with store.lock:
        draft = owned(owner, 'drafts', draft_id)
        if draft['confirmed']:
            return draft
        if body.expected_revision is not None and body.expected_revision != draft.get('revision', 0):
            raise HTTPException(409, '草稿已更新，请重新核对后保存')
        fields = work_fields(body, draft.get('fields'))
        try:
            calculation = calculate(fields)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if calculation['missing']:
            raise HTTPException(422, '请补充：' + '、'.join(calculation['missing']))
        if draft.get('source_entry_id'):
            try:
                entry = current_edit_entry(owner, draft)
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            _, rows = entry_update_rows(owner, entry, fields, calculation, draft)
            draft.update(fields=fields, calculation=calculation, confirmed=True)
            store.batch(owner, [('drafts', draft), *rows])
            return draft
        # Deterministic record IDs also protect retries after a lost network response.
        entry = {**item(), 'id': str(uuid.uuid5(uuid.UUID(draft_id), 'entry')), 'project_id': draft['project_id'],
                  'date': fields['date'], 'fields': fields, 'wage_fen': calculation['wage_fen'], 'draft_id': draft_id,
                  'source_text': draft.get('source_text', ''), 'revision_history': draft.get('revisions', [])}
        draft.update(fields=fields, calculation=calculation, confirmed=True)
        rows = [('drafts', draft), ('entries', entry), ('events', {**item(project_id=draft['project_id'],
                title='记工已由我核对', draft_id=draft_id, asset_id=draft.get('asset_id')), 'id': str(uuid.uuid5(uuid.UUID(draft_id), 'event'))})]
        rows += work_payment_rows(owner, entry, fields, calculation)
        store.batch(owner, rows)
        return draft


@app.patch(P + '/entries/{entry_id}')
def edit_entry(entry_id: str, body: Work, owner=Depends(identity)):
    with store.lock:
        entry = owned(owner, 'entries', entry_id)
        if body.expected_entry_version is not None and body.expected_entry_version != entry_version(entry):
            raise HTTPException(409, '这笔记工已更新，请返回账本重新打开')
        fields = work_fields(body, entry.get('fields'))
        try:
            result = calculate(fields)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if result['missing']:
            raise HTTPException(422, '请补充：' + '、'.join(result['missing']))
        entry, rows = entry_update_rows(owner, entry, fields, result)
        store.batch(owner, rows)
        return entry


class Payment(BaseModel):
    project_id: str
    date: Date
    amount: str
    request_id: str = Field(min_length=8, max_length=100)


@app.post(P + '/payments')
def payment(body: Payment, owner=Depends(identity)):
    owned(owner, 'projects', body.project_id)
    try:
        amount = cents(body.amount)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if amount <= 0:
        raise HTTPException(422, '金额须大于0')
    identifier = str(uuid.uuid5(uuid.UUID(owner), body.request_id))
    existing = store.get(owner, 'payments', identifier)
    if existing:
        return existing
    row = {**item(project_id=body.project_id, date=str(body.date), amount_fen=amount, type='received'), 'id': identifier}
    store.batch(owner, [('payments', row), ('events', {**item(project_id=body.project_id, title='收款已由我核对'),
                'id': str(uuid.uuid5(uuid.UUID(identifier), 'event'))})])
    return row


class Reconcile(BaseModel):
    task_id: str
    # User must review the extracted values and select the comparison scope.
    date: Date | None = None
    wage: str | None = None
    advance: str | None = None
    balance: str | None = None
    excerpt: str = Field(default='', max_length=6000)


@app.post(P + '/reports')
def report(body: Reconcile, owner=Depends(identity)):
    task = owned(owner, 'tasks', body.task_id)
    if task['type'] != 'reconcile' or task['status'] != 'completed':
        raise HTTPException(409, '截图尚未完成识别')
    if task.get('reused'):
        return reconciliation.present(owner, owned(owner, 'reports', task['result']['existing_report']['id']))
    return reconciliation.create(owner, task, body.model_dump(mode='json'))


reconciliation = Reconciliation(lambda: store, owned, totals)


class ReceiptDecision(BaseModel):
    received: bool
    confirmed: bool = False
    amount: str | None = None
    date: Date | None = None
    confirm_duplicate: bool = False


@app.post(P + '/reports/{report_id}/receipts/{receipt_id}')
def decide_receipt(report_id: str, receipt_id: str, body: ReceiptDecision, owner=Depends(identity)):
    return reconciliation.decide(owner, report_id, receipt_id, body.model_dump(mode='json'))


@app.get(P + '/projects/{project_id}/workspace')
def workspace(project_id: str, owner=Depends(identity)):
    return reconciliation.workspace(owner, project_id)


@app.get(P + '/projects/{project_id}/memory')
def project_memory(project_id: str, owner=Depends(identity)):
    return agent.context(store, owner, project_id)


@app.get(P + '/reports/{report_id}')
def get_report(report_id: str, owner=Depends(identity)):
    return reconciliation.present(owner, owned(owner, 'reports', report_id))


@app.post(P + '/tasks/{task_id}/dismiss')
def dismiss_processing(task_id: str, owner=Depends(identity)):
    with store.lock:
        task=owned(owner,'tasks',task_id)
        if task['status'] not in ('completed','failed'):
            raise HTTPException(409,'请等待当前处理结束')
        task['dismissed']=True
        return store.put(owner,'tasks',task)


@app.get(P + '/projects/{project_id}/timeline')
def timeline(project_id: str, owner=Depends(identity)):
    owned(owner, 'projects', project_id)
    assets = {a['id']: a for a in store.list(owner, 'assets') if a['project_id'] == project_id}
    reports = [r for r in store.list(owner, 'reports') if r['project_id'] == project_id]
    covered = {r['asset_id'] for r in reports}
    event_report_ids = set()
    events = []
    for event in store.list(owner, 'events'):
        if event['project_id'] != project_id:
            continue
        if event['title']=='原始资料已上传' and event.get('asset_id') in covered:
            continue
        if event.get('report_id'):
            if event['report_id'] in event_report_ids:
                continue
            event_report_ids.add(event['report_id'])
        asset = assets.get(event.get('asset_id'))
        if asset and not is_evidence(asset):
            if event['title'] == '原始资料已上传':
                continue
            event = {k: v for k, v in event.items() if k != 'asset_id'}
        events.append(event)
    return sorted(events, key=lambda r: r['created_at'], reverse=True)


@app.get(P + '/projects/{project_id}/statement')
def statement(project_id: str, owner=Depends(identity)):
    return compose_message(owner, project_id)


def compose_message(owner, project_id, report=None):
    memory=agent.context(store,owner,project_id)
    original_intent=ai.message_intent(memory,report)
    try:
        style=ai.message_style(memory,report)
        source='ai'
    except (ValueError, RuntimeError, httpx.HTTPError):
        style=ai.fallback_message_style(original_intent)
        source='fallback'
    memory=agent.context(store,owner,project_id)
    if report:
        report=owned(owner,'reports',report['id'])
    intent=ai.message_intent(memory,report)
    if intent!=original_intent:
        style=ai.fallback_message_style(intent)
        source='fallback'
    if intent=='payment_followup' and not any(word in style['closing'] for word in ('什么时候','啥时候','何时','付款时间','支付时间','结清时间')):
        style={**style,'closing':style['closing'].rstrip('。！？?!～~')+'。方便说下什么时候能付吗？'}
    t=memory['totals']
    period=memory['work_period']
    span=(period['start'] if period['start']==period['end'] else str(period['start'])+'至'+str(period['end'])) if period['start'] else ''
    facts=f"{memory['project']['name']}这边{span}已记工钱{t['wage_fen']/100:g}元，已收和借支共{t['advance_fen']/100:g}元，"
    facts+=f"按我这边记录还剩{t['balance_fen']/100:g}元待付。" if t['balance_fen']>0 else '本项目账面已经结清。' if t['balance_fen']==0 else f"账面多收{-t['balance_fen']/100:g}元，麻烦再核实一下。"
    if report:
        confirmed=sum(r['amount_fen'] for r in report.get('receipts',[]) if r['status']=='confirmed')
        pending=sum(r['amount_fen'] for r in report.get('receipts',[]) if r['status']=='pending')
        if confirmed and intent!='settled_ack':
            facts+=f"这次的{confirmed/100:g}元我确认收到了，已经记上。"
        elif pending:
            facts+='截图里提到的付款我还在核实到账情况，暂时没有记进已收。'
    greeting='' if style['opening'].startswith(memory['project']['boss']) else memory['project']['boss']+'，'
    return {'text':greeting+style['opening']+'\n'+facts+'\n'+style['closing'],
            'generated_by':source,'ledger_version':memory['ledger_version'],'intent':intent,'totals':t}


@app.get(P + '/reports/{report_id}/message')
def report_message(report_id: str, owner=Depends(identity)):
    report=owned(owner,'reports',report_id)
    return compose_message(owner,report['project_id'],report)


@app.get(P + '/projects/{project_id}/archive.pdf')
def export_pdf(project_id: str, owner=Depends(identity)):
    project = owned(owner, 'projects', project_id)
    snapshot = ledger(project_id, owner)
    # Totals and rows must describe the same captured ledger, even during a save.
    wage = sum(row['wage_fen'] for row in snapshot['entries'])
    paid = sum(row['amount_fen'] for row in snapshot['payments'])
    snapshot['totals'] = {'wage_fen': wage, 'advance_fen': paid, 'balance_fen': wage-paid}
    events = timeline(project_id, owner)
    drafts={d['id']:d for d in store.list(owner,'drafts') if d['project_id']==project_id}
    enriched=[]
    for event in events:
        record=event.get('after') or drafts.get(event.get('draft_id'))
        if record and record.get('fields'):
            event={**event,'work_date':record['fields'].get('date'),
                   'work_source':work_source(record.get('source_text',''),record.get('revision_history',record.get('revisions',[])))}
        enriched.append(event)
    events=enriched
    reports = [{**r, 'summary': reconciliation.summary(r)} for r in store.list(owner, 'reports') if r['project_id']==project_id]
    assets = [a for a in store.list(owner, 'assets') if a['project_id']==project_id and is_evidence(a)]
    try:
        data = render_archive(project, snapshot, events, reports, assets,
                              lambda a: asset_bytes(owner, a['id'])[1])
    except ValueError as error:
        raise HTTPException(409, str(error))
    except OSError:
        raise HTTPException(409, '原始凭据暂时无法读取，请稍后重新导出')
    filename = quote('务工档案证据线-'+project['name'][:36]+'.pdf', safe='')
    return Response(data, media_type='application/pdf', headers={
        'Content-Disposition': "attachment; filename=\"gongmingbai-archive.pdf\"; filename*=UTF-8''"+filename,
        'Cache-Control': 'private, no-store'})


@app.get(P + '/projects/{project_id}/export')
def export(project_id: str, owner=Depends(identity)):
    owned(owner, 'projects', project_id)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        entries = ledger(project_id, owner)
        archive.writestr('ledger.json', json.dumps(entries, ensure_ascii=False, indent=2))
        sheet = io.StringIO()
        writer = csv.writer(sheet)
        writer.writerow(['日期', '类型', '金额(元)'])
        for row in entries['entries']:
            writer.writerow([row['date'], '工钱', f"{row['wage_fen']/100:.2f}"])
        for row in entries['payments']:
            writer.writerow([row['date'], '已收/借支', f"{row['amount_fen']/100:.2f}"])
        archive.writestr('ledger.csv', sheet.getvalue().encode('utf-8-sig'))
        archive.writestr('timeline.json', json.dumps(timeline(project_id, owner), ensure_ascii=False, indent=2))
        reports = [r for r in store.list(owner, 'reports') if r['project_id'] == project_id]
        archive.writestr('reports.json', json.dumps(reports, ensure_ascii=False, indent=2))
        manifest = []
        for asset in store.list(owner, 'assets'):
            if asset['project_id'] != project_id or not is_evidence(asset):
                continue
            _, data = asset_bytes(owner, asset['id'])
            ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'audio/mpeg': '.mp3', 'audio/mp3': '.mp3', 'audio/wav': '.wav'}.get(asset['mime'], '.bin')
            filename = 'originals/' + asset['id'] + ext
            archive.writestr(filename, data)
            manifest.append({**asset, 'archive_path': filename})
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr('README.txt', '工明白项目资料\n金额以整数分存储。原件SHA256见manifest.json。资料整理供核对使用。\n')
    return Response(output.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="gongmingbai.zip"'})
