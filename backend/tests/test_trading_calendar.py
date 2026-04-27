from datetime import UTC, date, datetime

from app.core.trading_calendar import is_opening_buy_window, is_trading_time, previous_trading_day


def test_trading_time_rejects_weekend() -> None:
    assert is_trading_time(datetime(2026, 4, 25, 2, 0, tzinfo=UTC)) is False


def test_opening_buy_window_rejects_tail_session() -> None:
    assert is_opening_buy_window(datetime(2026, 4, 22, 6, 45, tzinfo=UTC)) is False


def test_previous_trading_day_skips_weekend() -> None:
    assert previous_trading_day(date(2026, 4, 27)).isoformat() == "2026-04-24"
