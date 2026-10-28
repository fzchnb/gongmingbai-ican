"""Durable reconciliation, receipt confirmation and one-time archival."""
from datetime import date, datetime, timezone
import uuid
from fastapi import HTTPException
from domain import cents, compare
import agent
from receipt_dates import suggest


def stamp():
    return datetime.now(timezone.utc).isoformat()


def identifier(parent, name):
    return str(uuid.uuid5(uuid.UUID(parent), name))


def proposals(extracted, parent):
    result = []
    values = extracted.get('payments') or []
    if not isinstance(values, list):
        return result
    for index, raw in enumerate(values[:10]):
        if not isinstance(raw, dict):
            continue
        try:
            amount = cents(raw.get('amount'))
            if amount <= 0:
                continue
            day = str(date.fromisoformat(raw['date'])) if raw.get('date') else None
        except (ValueError, TypeError):
            day = None
            try:
                amount = cents(raw.get('amount'))
                if amount <= 0:
                    continue
            except ValueError:
                continue
        result.append({'id': identifier(parent, 'receipt-'+str(index)), 'amount_fen': amount,
            'date': day, 'date_needs_confirmation': day is None, 'status': 'pending',
            'kind': raw.get('kind') if raw.get('kind') in ('transfer', 'promise', 'unclear') else 'unclear',
            'evidence': str(raw.get('evidence') or '')[:1000],
            'transaction_id': str(raw.get('transaction_id') or '')[:100]})
    return result


class Reconciliation:
    def __init__(self, get_store, owned, totals):
        self.get_store, self.owned, self.totals = get_store, owned, totals

    @property
    def store(self):
        return self.get_store()

    def archive_rows(self, owner, report):
        pending = any(r['status'] == 'pending' for r in report.get('receipts', []))
        report['status'] = 'awaiting_receipt' if pending else 'completed'
        if pending:
            return [('reports', report)]
        report['completed_at'] = report.get('completed_at') or stamp()
        asset = self.owned(owner, 'assets', report['asset_id'])
        asset.update(purpose='reconcile', archival_status='archived', report_id=report['id'])
        event = {'id': identifier(report['id'], 'event'), 'created_at': report['completed_at'],
                 'project_id': report['project_id'], 'title': '微信核账已完成',
                 'asset_id': asset['id'], 'report_id': report['id'],
                 'summary': self.summary(report)}
        return [('reports', report), ('assets', asset), ('events', event)]

    def summary(self, report):
        receipts = report.get('receipts', [])
        confirmed = sum(r['amount_fen'] for r in receipts if r['status'] == 'confirmed')
        if confirmed:
            return f"已确认到账{confirmed/100:g}元，已记入本项目账本；截图与核对结果已归档。"
        if any(r['status'] == 'pending' for r in receipts):
            return '发现付款信息，等待你确认是否实际到账；账本尚未增加收款。'
        return '已核对截图和账本，截图与核对结果已一起归档。'

    def create(self, owner, task, fields):
        with self.store.lock:
            self.owned(owner, 'projects', task['project_id'])
            extracted = task['result']['extracted']
            report_id = identifier(task['asset_id'], 'reconciliation')
            ledger_start = min((e['date'] for e in self.store.list(owner, 'entries')
                                if e['project_id'] == task['project_id']), default=None)
            receipts = [suggest(r, extracted, ledger_start) for r in proposals(extracted, report_id)]
            if not receipts and all(fields.get(k) in ('', None) for k in ('wage', 'advance', 'balance')):
                raise HTTPException(422, '没有明确金额，请核实截图中的工钱、余额或本次转账')
            # Same evidence has one workflow even if reuploaded/reanalyzed.
            previous = next((r for r in self.store.list(owner, 'reports') if r['project_id'] == task['project_id']
                             and r['asset_id'] == task['asset_id']), None)
            if previous:
                return self.present(owner, previous)
            scope = fields.get('date')
            try:
                rows = compare(self.totals(owner, task['project_id'], scope), fields)
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            memory = agent.context(self.store, owner, task['project_id'])
            report = {'id': report_id, 'created_at': stamp(), 'project_id': task['project_id'],
                'task_id': task['id'], 'asset_id': task['asset_id'], 'scope_date': scope,
                'excerpt': fields.get('excerpt', ''), 'chat_fields': fields, 'rows': rows,
                'receipts': receipts, 'context_version': memory['ledger_version'],
                'context_changed': memory['ledger_version'] != task.get('context', {}).get('ledger_version', memory['ledger_version']),
                'explanation': str(extracted.get('explanation') or extracted.get('note') or '')[:2000]}
            self.store.batch(owner, self.archive_rows(owner, report))
            return self.present(owner, report)

    def present(self, owner, report):
        result = {**report, 'summary': self.summary(report)}
        # Restore legacy pending workflows with suggestions without changing stored
        # reports, historical snapshots or confirmed receipts on a read request.
        if any(r.get('status') == 'pending' and not r.get('date_source') for r in report.get('receipts', [])):
            task = self.store.get(owner, 'tasks', report.get('task_id')) if report.get('task_id') else None
            extracted = (task.get('result', {}).get('extracted') or {}) if task and task.get('project_id') == report['project_id'] and task.get('asset_id') == report.get('asset_id') else {}
            extracted = {**report.get('chat_fields', {}), **extracted}
            ledger_start = min((e['date'] for e in self.store.list(owner, 'entries')
                                if e['project_id'] == report['project_id']), default=None)
            result['receipts'] = [suggest(r, extracted, ledger_start) for r in report.get('receipts', [])]
        # Current ledger, rather than a stale generated paragraph, is authoritative.
        result['totals'] = self.totals(owner, report['project_id'])
        return result

    def decide(self, owner, report_id, receipt_id, body):
        with self.store.lock:
            report = self.owned(owner, 'reports', report_id)
            receipt = next((r for r in report.get('receipts', []) if r['id'] == receipt_id), None)
            if not receipt:
                raise HTTPException(404, '待确认收款不存在')
            if receipt['status'] != 'pending':
                return self.present(owner, report)
            rows = []
            if body['received']:
                if not body.get('confirmed'):
                    raise HTTPException(400, '请先确认已经实际到账')
                if not body.get('date'):
                    raise HTTPException(422, '请核对实际到账日期')
                if body['date'] > agent.today():
                    raise HTTPException(422, '实际到账日期不能晚于今天，请重新核对')
                try:
                    amount = cents(body['amount'])
                    if amount <= 0:
                        raise ValueError('收款金额须大于0')
                except ValueError as exc:
                    raise HTTPException(422, str(exc))
                payments = [p for p in self.store.list(owner, 'payments') if p['project_id'] == report['project_id']]
                transaction = receipt.get('transaction_id')
                same_transaction = next((p for p in payments if transaction and p.get('transaction_id') == transaction), None)
                if same_transaction:
                    if same_transaction['amount_fen'] != amount or same_transaction['date'] != body['date']:
                        raise HTTPException(422, '相同交易号已记账，但金额或日期不同，请先核实账本中的收款')
                    receipt.update(status='already_recorded', payment_id=same_transaction['id'], date_needs_confirmation=False)
                else:
                    duplicate = next((p for p in payments if p['date'] == body['date'] and p['amount_fen'] == amount
                                      and p.get('type') == 'received'), None)
                    if duplicate and not body.get('confirm_duplicate'):
                        raise HTTPException(409, '当天已有一笔相同金额收款，请核对是否为另一笔到账')
                    payment = {'id': identifier(receipt_id, 'payment'), 'created_at': stamp(), 'project_id': report['project_id'],
                               'date': body['date'], 'amount_fen': amount, 'type': 'received',
                               'report_id': report_id, 'receipt_id': receipt_id, 'asset_id': report['asset_id'],
                               'transaction_id': transaction}
                    rows.append(('payments', payment))
                    receipt.update(status='confirmed', payment_id=payment['id'], amount_fen=amount, date=body['date'], date_needs_confirmation=False)
            else:
                receipt['status'] = 'not_received'
            receipt['decided_at'] = stamp()
            # The receipt and archive commit atomically with the payment.
            rows += self.archive_rows(owner, report)
            self.store.batch(owner, rows)
            return self.present(owner, report)

    def workspace(self, owner, project_id):
        self.owned(owner, 'projects', project_id)
        reports = [r for r in self.store.list(owner, 'reports') if r['project_id'] == project_id]
        reports.sort(key=lambda r: r['created_at'], reverse=True)
        covered = {r['asset_id'] for r in reports}
        tasks = [t for t in self.store.list(owner, 'tasks') if t['project_id'] == project_id and t['type'] == 'reconcile'
                 and t.get('asset_id') not in covered and not t.get('dismissed')]
        tasks.sort(key=lambda t: t['created_at'], reverse=True)
        pending = [self.present(owner, r) for r in reports if any(p['status'] == 'pending' for p in r.get('receipts', []))]
        return {'pending_reports': pending, 'latest_report': self.present(owner, reports[0]) if reports else None,
                'active_task': tasks[0] if tasks else None}
