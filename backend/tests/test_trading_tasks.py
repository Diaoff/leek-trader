import logging

from app.tasks.trading_tasks import match_pending_orders_task


def test_match_pending_orders_task_runs(client, monkeypatch) -> None:
    import app.tasks.trading_tasks as trading_tasks

    monkeypatch.setattr(trading_tasks.TradingService, "match_pending_orders", lambda self, db: {"status": "accepted", "matched_count": 0, "matched_orders": []})

    result = match_pending_orders_task()

    assert result["status"] == "accepted"
    assert result["matched_count"] == 0


def test_trading_task_uses_retry_policy_and_logs_success(client, monkeypatch, caplog) -> None:
    import app.tasks.trading_tasks as trading_tasks

    monkeypatch.setattr(
        trading_tasks.TradingService,
        "match_pending_orders",
        lambda self, db: {"status": "accepted", "matched_count": 2, "matched_orders": [1, 2]},
    )

    with caplog.at_level(logging.INFO):
        result = match_pending_orders_task()

    assert result["matched_count"] == 2
    assert match_pending_orders_task.autoretry_for == (Exception,)
    assert match_pending_orders_task.retry_backoff is True
    assert match_pending_orders_task.retry_kwargs["max_retries"] == 3
    assert "Celery task started task=app.tasks.trading_tasks.match_pending_orders_task" in caplog.text
    assert "Celery task succeeded task=app.tasks.trading_tasks.match_pending_orders_task" in caplog.text
