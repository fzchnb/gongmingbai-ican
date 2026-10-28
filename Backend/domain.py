"""Amounts are integer fen. Models extract facts; this module alone calculates wages."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta


def number(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('请输入有效数字')
    if not n.is_finite() or n < 0 or n > Decimal('100000000'):
        raise ValueError('数字超出有效范围')
    return n


def cents(value):
    return int((number(value) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def calculate(draft):
    missing = []
    for key, label in [('date', '日期'), ('days', '天数'), ('day_rate', '日单价')]:
        if draft.get(key) in (None, ''):
            missing.append(label)
    hours = number(draft.get('overtime_hours') or 0)
    if hours and draft.get('overtime_rate') in (None, ''):
        missing.append('加班单价')
    if missing:
        return {'missing': missing, 'wage_fen': None, 'advance_fen': None, 'received_fen': None, 'balance_fen': None}
    base = number(draft['days']) * number(draft['day_rate'])
    overtime = hours * number(draft.get('overtime_rate') or 0)
    wage, advance = cents(base + overtime), cents(draft.get('advance') or 0)
    received = max(wage - advance, 0) if draft.get('settled') is True else cents(draft.get('received') or 0)
    received_day = draft.get('received_date') or draft['date']
    if received and str(received_day) > datetime.now(timezone(timedelta(hours=8))).date().isoformat():
        raise ValueError('实际到账日期不能晚于今天，请核对本笔收款日期')
    return {'missing': [], 'wage_fen': wage, 'advance_fen': advance,
            'received_fen': received, 'balance_fen': wage - advance - received}


def compare(ledger, chat):
    rows = []
    for key, label in [('wage_fen', '工钱'), ('advance_fen', '已收/借支'), ('balance_fen', '待付')]:
        raw = chat.get(key.replace('_fen', ''))
        other = cents(raw) if raw is not None and raw != '' else None
        rows.append({'label': label, 'mine_fen': ledger[key], 'chat_fen': other,
                     'difference_fen': ledger[key] - other if other is not None else None})
    return rows
