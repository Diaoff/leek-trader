import logging

from app.core.celery_app import celery_app
from app.tasks.market_tasks import refresh_market_quotes, refresh_market_quotes_task, run_market_research_task


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
            "status": "refreshed",
            "task": "refresh_market_quotes",
            "symbols": symbols,
            "count": len(symbols or []),
        },
    )

    result = refresh_market_quotes()

    assert result["symbols"] == market_tasks.settings.market_refresh_symbol_list
    assert result["count"] == len(market_tasks.settings.market_refresh_symbol_list)


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


def test_celery_enables_task_started_events() -> None:
    assert celery_app.conf.task_track_started is True
    assert celery_app.conf.task_send_sent_event is True


def test_run_market_research_task_executes_service(client, monkeypatch) -> None:
    import app.tasks.market_tasks as market_tasks

    monkeypatch.setattr(
        market_tasks.MarketResearchService,
        "execute_run",
        lambda self, db, run_id=None, task_id=None, triggered_by="system": type(
            "Run",
            (),
            {"id": 9, "recommendation_count": 6},
        )(),
    )

    result = run_market_research_task(run_id=9, triggered_by="manual")

    assert result["status"] == "completed"
    assert result["task"] == "run_market_research"
    assert result["run_id"] == 9
    assert result["recommendation_count"] == 6
