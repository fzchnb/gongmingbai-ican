"""Receipt date suggestions only; never constitute confirmation of payment."""
from datetime import date
import re
import agent


# Require a full year: an isolated time, amount or month/day is not a date.
FULL_DATE = re.compile(r'(?<!\d)(\d{4})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})(?:\s*日)?(?!\d)')


def valid_day(value):
    try:
        day = date.fromisoformat(str(value))
        return day.isoformat() if day.isoformat() <= agent.today() else None
    except (ValueError, TypeError):
        return None


def text_days(text):
    result = set()
    for year, month, day in FULL_DATE.findall(str(text or '')[:20000]):
        try:
            value = valid_day(date(int(year), int(month), int(day)))
            if value:
                result.add(value)
        except ValueError:
            pass
    return result


def suggest(receipt, extracted, ledger_start):
    """Prefer transfer date, then screenshot/message date, then ledger start.

    Multiple message dates (e.g. a work period) are ambiguous, so use the
    explicitly labelled ledger fallback rather than guessing a transfer day.
    """
    result = receipt.copy()
    if result.get('status') != 'pending' or result.get('date_source'):
        return result
    day = valid_day(receipt.get('date'))
    source = 'transfer' if day else None
    if not day:
        day = valid_day(extracted.get('screenshot_date'))
        source = 'screenshot' if day else None
    if not day:
        for text in (receipt.get('evidence'),
                     str(extracted.get('visible_text') or '') + '\n' + str(extracted.get('excerpt') or '')):
            candidates = text_days(text)
            if len(candidates) == 1:
                day, source = next(iter(candidates)), 'message'
                break
    if not day:
        day = valid_day(ledger_start)
        source = 'ledger_start' if day else None
    hints = {
        'transfer': '已按截图中的转账日期预填，请核对实际到账日期。',
        'screenshot': '已按截图标注的日期预填，可能与实际到账日不同，请核对。',
        'message': '已按截图消息中的完整日期预填，可能是记工日期，请核对实际到账日。',
        'ledger_start': '截图未明确到账日期，已按本项目账本开始日期预填，请核对实际到账日。',
    }
    result.update(date=day, date_source=source,
                  date_needs_confirmation=source != 'transfer',
                  date_hint=hints.get(source, '截图没有可用日期，本项目也没有已确认记工，请填写实际到账日期。'))
    return result
