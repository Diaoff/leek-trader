import logging

from app.core.celery_app import celery_app
from app.tasks.market_tasks import refresh_market_quotes, refresh_market_quotes_task


def test_refresh_market_quotes_task_warms_symbols(client, monkeypatch) -> None:
    import app.tasks.market_tasks as market_tasks

    monkeypatch.setattr(
        market_tasks.QuoteService,
        "refresh_quotes",
        lambda self, symbols=None: [
            type("Quote", (), {"symbol": "sh600519"})(),
            type("Quote", (), {"symbol": "sz000001"})(),
        ],
    )

    result = refresh_market_quotes_task(["sh600519", "sz000001"])

    assert result["status"] == "refreshed"
    assert result["task"] == "refresh_market_quotes"
    assert result["count"] == 2
    assert result["symbols"] == ["sh600519", "sz000001"]


def test_refresh_market_quotes_wrapper_uses_default_configured_symbols(client, monkeypatch) -> None:
    import app.tasks.market_tasks as market_tasks

    monkeypatch.setattr(
        market_tasks,
        "refresh_market_quotes_task",
        lambda symbols=None: {
            "status": "skipped" if not symbols else "refreshed",
            "task": "refresh_market_quotes",
            "symbols": symbols or [],
            "count": len(symbols or []),
        },
    )

    result = refresh_market_quotes()

    assert result["symbols"] == []
    assert result["count"] == 0


def test_market_task_uses_retry_policy_and_logs_success(client, monkeypatch, caplog) -> None:
    import app.tasks.market_tasks as market_tasks

    monkeypatch.setattr(
        market_tasks.QuoteService,
        "refresh_quotes",
        lambda self, symbols=None: [type("Quote", (), {"symbol": "sh600519"})()],
    )

    with caplog.at_level(logging.INFO):
        result = refresh_market_quotes_task(["sh600519"])

    assert result["count"] == 1
    assert refresh_market_quotes_task.autoretry_for == (Exception,)
    assert refresh_market_quotes_task.retry_backoff is True
    assert refresh_market_quotes_task.retry_kwargs["max_retries"] == 3
    assert "Celery task started task=app.tasks.market_tasks.refresh_market_quotes_task" in caplog.text
    assert "Celery task succeeded task=app.tasks.market_tasks.refresh_market_quotes_task" in caplog.text


def test_refresh_market_quotes_task_skips_when_no_symbols_available(client) -> None:
    result = refresh_market_quotes_task([])

    assert result["status"] == "skipped"
    assert result["symbols"] == []
    assert result["count"] == 0


def test_refresh_market_quotes_task_skips_scheduled_outside_trading_hours(client, monkeypatch) -> None:
    import app.tasks.market_tasks as market_tasks

    monkeypatch.setattr(market_tasks, "is_trading_time", lambda: False)
    monkeypatch.setattr(
        market_tasks.QuoteService,
        "refresh_quotes",
        lambda self, symbols=None: (_ for _ in ()).throw(AssertionError("scheduled task should not refresh quotes outside trading hours")),
    )

    result = refresh_market_quotes_task(["sh600519"], scheduled=True)

    assert result == {
        "status": "skipped",
        "task": "refresh_market_quotes",
        "reason": "outside_trading_hours",
        "scheduled": True,
    }


def test_refresh_market_quotes_task_manual_executes_outside_trading_hours(client, monkeypatch) -> None:
    import app.tasks.market_tasks as market_tasks

    monkeypatch.setattr(market_tasks, "is_trading_time", lambda: False)
    monkeypatch.setattr(
        market_tasks.QuoteService,
        "refresh_quotes",
        lambda self, symbols=None: [type("Quote", (), {"symbol": symbol})() for symbol in symbols],
    )

    result = refresh_market_quotes_task(["sh600519"])

    assert result["status"] == "refreshed"
    assert result["count"] == 1


def test_celery_registers_market_schedule_as_scheduled() -> None:
    assert celery_app.conf.beat_schedule["refresh-market-quotes"]["kwargs"] == {"scheduled": True}
    assert "scheduled" not in celery_app.conf.beat_schedule["run-smart-selection"].get("kwargs", {})


def test_celery_enables_task_started_events() -> None:
    assert celery_app.conf.task_track_started is True
    assert celery_app.conf.task_send_sent_event is True
