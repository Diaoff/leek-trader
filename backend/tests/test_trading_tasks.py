import logging

from app.core.celery_app import celery_app
from app.tasks.trading_tasks import match_pending_orders_task, monitor_position_guards_task


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


def test_monitor_position_guards_task_runs(client, monkeypatch) -> None:
    import app.tasks.trading_tasks as trading_tasks

    monkeypatch.setattr(
        trading_tasks.TradingService,
        "monitor_position_guards",
        lambda self, db: {"status": "accepted", "scanned_count": 1, "triggered_count": 1, "triggered_orders": [{"symbol": "sh600519"}], "skipped": []},
    )

    result = monitor_position_guards_task()

    assert result["status"] == "accepted"
    assert result["triggered_count"] == 1


def test_match_pending_orders_task_skips_scheduled_outside_trading_hours(client, monkeypatch) -> None:
    import app.tasks.trading_tasks as trading_tasks

    monkeypatch.setattr(trading_tasks, "is_trading_time", lambda: False)
    monkeypatch.setattr(
        trading_tasks.TradingService,
        "match_pending_orders",
        lambda self, db: (_ for _ in ()).throw(AssertionError("scheduled task should not match orders outside trading hours")),
    )

    result = match_pending_orders_task(scheduled=True)

    assert result == {
        "status": "skipped",
        "task": "match_pending_orders",
        "reason": "outside_trading_hours",
        "scheduled": True,
    }


def test_match_pending_orders_task_manual_executes_outside_trading_hours(client, monkeypatch) -> None:
    import app.tasks.trading_tasks as trading_tasks

    monkeypatch.setattr(trading_tasks, "is_trading_time", lambda: False)
    monkeypatch.setattr(
        trading_tasks.TradingService,
        "match_pending_orders",
        lambda self, db: {"status": "accepted", "matched_count": 1, "matched_orders": [1]},
    )

    result = match_pending_orders_task()

    assert result["status"] == "accepted"
    assert result["matched_count"] == 1


def test_monitor_position_guards_task_skips_scheduled_outside_trading_hours(client, monkeypatch) -> None:
    import app.tasks.trading_tasks as trading_tasks

    monkeypatch.setattr(trading_tasks, "is_trading_time", lambda: False)
    monkeypatch.setattr(
        trading_tasks.TradingService,
        "monitor_position_guards",
        lambda self, db: (_ for _ in ()).throw(AssertionError("scheduled task should not monitor guards outside trading hours")),
    )

    result = monitor_position_guards_task(scheduled=True)

    assert result == {
        "status": "skipped",
        "task": "monitor_position_guards",
        "reason": "outside_trading_hours",
        "scheduled": True,
    }


def test_monitor_position_guards_task_manual_executes_outside_trading_hours(client, monkeypatch) -> None:
    import app.tasks.trading_tasks as trading_tasks

    monkeypatch.setattr(trading_tasks, "is_trading_time", lambda: False)
    monkeypatch.setattr(
        trading_tasks.TradingService,
        "monitor_position_guards",
        lambda self, db: {"status": "accepted", "scanned_count": 1, "triggered_count": 0, "triggered_orders": [], "skipped": []},
    )

    result = monitor_position_guards_task()

    assert result["status"] == "accepted"
    assert result["triggered_count"] == 0


def test_monitor_position_guards_task_uses_retry_policy_and_logs_success(client, monkeypatch, caplog) -> None:
    import app.tasks.trading_tasks as trading_tasks

    monkeypatch.setattr(
        trading_tasks.TradingService,
        "monitor_position_guards",
        lambda self, db: {"status": "accepted", "scanned_count": 2, "triggered_count": 1, "triggered_orders": [1], "skipped": []},
    )

    with caplog.at_level(logging.INFO):
        result = monitor_position_guards_task()

    assert result["triggered_count"] == 1
    assert monitor_position_guards_task.autoretry_for == (Exception,)
    assert monitor_position_guards_task.retry_backoff is True
    assert monitor_position_guards_task.retry_kwargs["max_retries"] == 3
    assert "Celery task started task=app.tasks.trading_tasks.monitor_position_guards_task" in caplog.text
    assert "Celery task succeeded task=app.tasks.trading_tasks.monitor_position_guards_task" in caplog.text


def test_celery_registers_position_guard_schedule() -> None:
    assert "app.tasks.trading_tasks" in celery_app.conf.imports
    assert celery_app.conf.beat_schedule["monitor-position-guards"]["task"] == "app.tasks.trading_tasks.monitor_position_guards_task"
    assert celery_app.conf.beat_schedule["match-pending-orders"]["kwargs"] == {"scheduled": True}
    assert celery_app.conf.beat_schedule["monitor-position-guards"]["kwargs"] == {"scheduled": True}
