from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


MARKET_TIMEZONE = ZoneInfo("Asia/Shanghai")
TRADING_SESSION_WINDOWS = (
    (time(9, 30), time(11, 30)),
    (time(13, 0), time(15, 0)),
)
OPENING_BUY_WINDOWS = (
    (time(9, 35), time(11, 20)),
    (time(13, 0), time(14, 30)),
)


def market_now() -> datetime:
    return datetime.now(MARKET_TIMEZONE)


def to_market_datetime(value: datetime | None = None) -> datetime:
    if value is None:
        return market_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=MARKET_TIMEZONE)
    return value.astimezone(MARKET_TIMEZONE)


def market_trade_date(value: date | datetime | None = None) -> date:
    if value is None:
        return market_now().date()
    if isinstance(value, datetime):
        return to_market_datetime(value).date()
    return value


def is_trading_day(value: date | datetime | None = None) -> bool:
    return market_trade_date(value).weekday() < 5


def previous_trading_day(value: date | datetime | None = None) -> date:
    current = market_trade_date(value) - timedelta(days=1)
    while not is_trading_day(current):
        current -= timedelta(days=1)
    return current


def is_trading_time(now: datetime | None = None) -> bool:
    return _is_within_windows(now, TRADING_SESSION_WINDOWS)


def is_opening_buy_window(now: datetime | None = None) -> bool:
    return _is_within_windows(now, OPENING_BUY_WINDOWS)


def _is_within_windows(now: datetime | None, windows: tuple[tuple[time, time], ...]) -> bool:
    current = to_market_datetime(now)
    if not is_trading_day(current.date()):
        return False
    current_time = current.time().replace(tzinfo=None)
    return any(start <= current_time <= end for start, end in windows)
