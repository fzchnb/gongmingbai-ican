"""Small record repository. Cloud writes use an atomic Supabase RPC."""
import json
import os
import sqlite3
import threading
from pathlib import Path
import httpx


class Store:
    def __init__(self):
        self.root = Path(os.getenv('DATA_DIR', str(Path(__file__).parent / 'data')))
        self.root.mkdir(parents=True, exist_ok=True)
        self.url = os.getenv('SUPABASE_URL', '').rstrip('/')
        self.key = os.getenv('SUPABASE_SECRET_KEY', '')
        self.cloud = bool(self.url and self.key)
        self.lock = threading.RLock()
        self.client = httpx.Client(timeout=30)
        if not self.cloud:
            with self.db() as db:
                db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, owner_id TEXT, kind TEXT, payload TEXT)')
                db.execute('CREATE TABLE IF NOT EXISTS accounts (phone TEXT PRIMARY KEY, owner_id TEXT UNIQUE, salt TEXT, password_hash TEXT)')
                db.execute('CREATE TABLE IF NOT EXISTS revoked_tokens (digest TEXT PRIMARY KEY)')

    def db(self):
        db = sqlite3.connect(self.root / 'app.sqlite', timeout=15)
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def remote(self, method, route, **kwargs):
        for attempt in range(2):
            try:
                response = self.client.request(method, self.url + route, headers={
                    'apikey': self.key, 'Authorization': 'Bearer ' + self.key,
                    'Prefer': 'return=representation'}, **kwargs)
                break
            except httpx.RequestError:
                if attempt:
                    raise
        response.raise_for_status()
        return response.json() if response.content else None

    def list(self, owner, kind):
        if self.cloud:
            data = self.remote('GET', '/rest/v1/records', params={
                'owner_id': 'eq.' + owner, 'kind': 'eq.' + kind, 'select': 'payload', 'order': 'created_at.asc', 'limit': '10000'})
            return [r['payload'] for r in data]
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute(
                'SELECT payload FROM records WHERE owner_id=? AND kind=? ORDER BY rowid', (owner, kind))]

    def all_tasks(self):
        if self.cloud:
            return [{**r['payload'], 'id': r['id'], 'owner_id': r['owner_id']} for r in self.remote('GET', '/rest/v1/records', params={
                'kind': 'eq.tasks', 'select': 'id,owner_id,payload', 'payload->>status': 'in.(queued,running)'})]
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM records WHERE kind='tasks'")
                    if json.loads(r[0])['status'] in ('queued', 'running')]

    def get(self, owner, kind, identifier):
        return next((r for r in self.list(owner, kind) if r['id'] == identifier), None)

    def batch(self, owner, rows):
        if self.cloud:
            return self.remote('POST', '/rest/v1/rpc/write_records', json={
                'p_owner': owner, 'p_rows': [{'id': r['id'], 'kind': k, 'payload': r} for k, r in rows]})
        with self.lock, self.db() as db:
            for kind, row in rows:
                old = db.execute('SELECT owner_id FROM records WHERE id=?', (row['id'],)).fetchone()
                if old and old[0] != owner:
                    raise ValueError('记录归属不匹配')
                db.execute('INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                           (row['id'], owner, kind, json.dumps(row, ensure_ascii=False)))

    def put(self, owner, kind, row):
        self.batch(owner, [(kind, row)])
        return row
