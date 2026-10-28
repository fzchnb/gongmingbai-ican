"""Shared, grounded project memory. Every model operation reads the same tools."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException


def today():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def context(store, owner, project_id):
    project = store.get(owner, 'projects', project_id)
    if not project or project.get('deleted_at'):
        raise HTTPException(404, '项目不存在或已删除')
    records = {kind: [r for r in store.list(owner, kind) if r.get('project_id') == project_id]
               for kind in ('entries', 'payments', 'reports')}
    entries, payments = records['entries'], records['payments']
    payments = [p for p in payments if p['amount_fen']>0]
    wage = sum(e['wage_fen'] for e in entries)
    paid = sum(p['amount_fen'] for p in payments)
    days = {}
    for entry in entries:
        day = days.setdefault(entry['date'], {'wage_fen': 0, 'advance_fen': 0})
        day['wage_fen'] += entry['wage_fen']
    for payment in payments:
        day = days.setdefault(payment['date'], {'wage_fen': 0, 'advance_fen': 0})
        day['advance_fen'] += payment['amount_fen']
    ledger_version = digest({'entries': entries, 'payments': payments})
    return {'project': {'id': project_id, 'name': project['name'], 'boss': project['boss']},
            'today': today(), 'timezone': 'Asia/Shanghai', 'ledger_version': ledger_version,
            'totals': {'wage_fen': wage, 'advance_fen': paid, 'balance_fen': wage-paid},
            'work_period': {'start': min((e['date'] for e in entries), default=None),
                            'end': max((e['date'] for e in entries), default=None)},
            'day_totals': {day:days[day] for day in sorted(days)[-120:]},
            'entries': [{'id':e['id'], 'date':e['date'], 'wage_fen':e['wage_fen'],
                         'fields':{k:e['fields'].get(k) for k in ('date','days','day_rate','overtime_hours','overtime_rate','advance','received','settled','received_date')}}
                        for e in sorted(entries, key=lambda e:e['date'])[-60:]],
            'payments': [{k:p.get(k) for k in ('id','date','amount_fen','type','report_id')}
                         for p in sorted(payments,key=lambda p:p['date'])[-40:]],
            'reconciliations': [{**{k:r.get(k) for k in ('id','created_at','scope_date','rows','status')},
                'rows_are_historical_snapshot':True,
                'explanation':str(r.get('explanation') or '')[:500],
                'receipts':[{k:v.get(k) for k in ('id','amount_fen','date','status','kind')}
                            for v in r.get('receipts',[])]} for r in records['reports'][-8:]],
            'truncated': len(entries)>60 or len(payments)>40 or len(records['reports'])>8 or len(days)>120,
            'counts':{kind:len(rows) for kind,rows in records.items()},
            'tools_used': ['read_project', 'read_confirmed_ledger', 'read_payment_history', 'read_reconciliation_history'],
            'rules': '金额为整数分。当前totals/账本/已确认收款为事实；历史核账rows是核账前快照，不能覆盖当前余额。待确认收款、截图及识别解释不是已到账事实。新记工不得复制历史待收为工资。本笔结清不能冲销其他欠款。不得跨项目。'}
