"""Conservative EOD freshness and next-open order-window checks.

This intentionally uses weekdays, not an asserted NSE holiday calendar. A weekday
holiday may show 'Verify session' and block new orders until data is refreshed.
No intraday bar is accepted as a completed daily observation.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
DATA_READY_AFTER = time(16, 15)
NEXT_OPEN = time(9, 15)


def now_ist() -> datetime:
    return datetime.now(IST)


def completed_cutoff(now: datetime | None = None) -> date:
    current = (now or now_ist()).astimezone(IST)
    day = current.date()
    if current.time().replace(tzinfo=None) < DATA_READY_AFTER:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def next_weekday(day: date) -> date:
    following = day + timedelta(days=1)
    while following.weekday() >= 5:
        following += timedelta(days=1)
    return following


def freshness(as_of: str | None, now: datetime | None = None) -> dict:
    expected = completed_cutoff(now)
    if not as_of:
        return {"status": "Missing", "is_fresh": False, "expected": expected.isoformat(), "age_days": None}
    try:
        observed = date.fromisoformat(as_of)
    except (ValueError, TypeError):
        return {"status": "Invalid date", "is_fresh": False, "expected": expected.isoformat(), "age_days": None}
    age = (expected - observed).days
    return {"status": "Current EOD" if age == 0 else "Stale / verify session" if age > 0 else "Future / incomplete",
            "is_fresh": age == 0, "expected": expected.isoformat(), "age_days": age}


def order_window(signal_date: str, now: datetime | None = None) -> tuple[bool, str]:
    current = (now or now_ist()).astimezone(IST)
    signal = date.fromisoformat(signal_date)
    ready = datetime.combine(signal, DATA_READY_AFTER, IST)
    deadline = datetime.combine(next_weekday(signal), NEXT_OPEN, IST)
    if current < ready:
        return False, "Wait for a completed EOD snapshot."
    if current >= deadline:
        return False, "Next-open entry window has passed. Wait for a new EOD setup; historical fills are not created."
    return True, f"Pending order may enter the next observed session after {signal_date}."
