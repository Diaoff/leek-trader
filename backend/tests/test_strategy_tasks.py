import logging

from app.core.celery_app import celery_app
from app.market.providers.base import DailyBarSnapshot


def _build_bars(symbol: str) -> list[DailyBarSnapshot]:
    from datetime import date, timedelta

    base = date(2026, 4, 1)
    closes = [10, 10, 10, 10, 10, 9, 8, 9, 10, 12]
    return [
        DailyBarSnapshot(
            symbol=symbol,
            trade_date=base + timedelta(days=index),
            open_price=close * 0.99,
            close_price=close,
            high_price=close * 1.01,
            low_price=close * 0.98,
            volume=1_000_000 + index * 10_000,
        )
        for index, close in enumerate(closes)
    ]


def test_run_strategy_cycle_task_executes_active_strategies(client, monkeypatch) -> None:
    import app.core.db as db_module
    import app.tasks.strategy_tasks as strategy_tasks
    from app.strategy.service import StrategyService

    monkeypatch.setattr(strategy_tasks, "SessionLocal", db_module.SessionLocal)
    monkeypatch.setattr(StrategyService, "_load_price_bars", lambda self, symbol, limit: _build_bars(symbol))

    created_ids: list[int] = []
    for index, symbol in enumerate(["sh600036", "sh600519"], start=1):
        created = client.post(
            "/api/v1/strategies",
            json={
                "name": f"任务策略{index}",
                "symbol": symbol,
                "strategy_type": "moving_average",
                "execution_mode": "signal_only",
                "parameters": {"short_window": 5, "long_window": 20},
            },
        ).json()
        created_ids.append(created["id"])
        client.patch(
            f"/api/v1/strategies/{created['id']}",
            json={"status": "active"},
        )

    result = strategy_tasks.run_strategy_cycle_task()

    assert result["status"] == "completed"
    assert result["task"] == "run_strategy_cycle"
    assert result["count"] == 2
    assert result["strategy_ids"] == created_ids
    assert {item["status"] for item in result["results"]} == {"success"}


def test_run_strategy_cycle_task_with_empty_strategy_ids_runs_none(client, monkeypatch) -> None:
    import app.core.db as db_module
    import app.tasks.strategy_tasks as strategy_tasks

    monkeypatch.setattr(strategy_tasks, "SessionLocal", db_module.SessionLocal)

    result = strategy_tasks.run_strategy_cycle_task([])

    assert result["status"] == "completed"
    assert result["count"] == 0
    assert result["strategy_ids"] == []
    assert result["results"] == []


def test_celery_registers_strategy_cycle_schedule() -> None:
    assert "app.tasks.strategy_tasks" in celery_app.conf.imports
    assert celery_app.conf.beat_schedule["run-strategy-cycle"]["task"] == "app.tasks.strategy_tasks.run_strategy_cycle_task"
    assert celery_app.conf.beat_schedule["run-strategy-cycle"]["kwargs"] == {"scheduled": True}


def test_run_strategy_cycle_task_skips_scheduled_outside_trading_hours(client, monkeypatch) -> None:
    import app.core.db as db_module
    import app.tasks.strategy_tasks as strategy_tasks

    def fail_if_called(self, db, strategy_ids=None):
        raise AssertionError("scheduled task should not run strategies outside trading hours")

    monkeypatch.setattr(strategy_tasks, "SessionLocal", db_module.SessionLocal)
    monkeypatch.setattr(strategy_tasks, "is_trading_time", lambda: False)
    monkeypatch.setattr(strategy_tasks.StrategyService, "run_active_strategies", fail_if_called)

    result = strategy_tasks.run_strategy_cycle_task(scheduled=True)

    assert result == {
        "status": "skipped",
        "task": "run_strategy_cycle",
        "reason": "outside_trading_hours",
        "scheduled": True,
        "strategy_ids": [],
    }


def test_run_strategy_cycle_task_manual_executes_outside_trading_hours(client, monkeypatch) -> None:
    import app.core.db as db_module
    import app.tasks.strategy_tasks as strategy_tasks

    called = False

    def fake_run_active_strategies(self, db, strategy_ids=None):
        nonlocal called
        called = True
        assert strategy_ids == [1]
        return []

    monkeypatch.setattr(strategy_tasks, "SessionLocal", db_module.SessionLocal)
    monkeypatch.setattr(strategy_tasks, "is_trading_time", lambda: False)
    monkeypatch.setattr(strategy_tasks.StrategyService, "run_active_strategies", fake_run_active_strategies)

    result = strategy_tasks.run_strategy_cycle_task([1])

    assert called is True
    assert result["status"] == "completed"
    assert result["strategy_ids"] == []


def test_strategy_task_uses_retry_policy_and_logs_success(client, monkeypatch, caplog) -> None:
    import app.core.db as db_module
    import app.tasks.strategy_tasks as strategy_tasks
    from app.strategy.service import StrategyService

    monkeypatch.setattr(strategy_tasks, "SessionLocal", db_module.SessionLocal)
    monkeypatch.setattr(StrategyService, "_load_price_bars", lambda self, symbol, limit: _build_bars(symbol))

    with caplog.at_level(logging.INFO):
        result = strategy_tasks.run_strategy_cycle_task([])

    assert result["count"] == 0
    assert strategy_tasks.run_strategy_cycle_task.autoretry_for == (Exception,)
    assert strategy_tasks.run_strategy_cycle_task.retry_backoff is True
    assert strategy_tasks.run_strategy_cycle_task.retry_kwargs["max_retries"] == 3
    assert "Celery task started task=app.tasks.strategy_tasks.run_strategy_cycle_task" in caplog.text
    assert "Celery task succeeded task=app.tasks.strategy_tasks.run_strategy_cycle_task" in caplog.text


def test_run_strategy_cycle_task_skips_when_scheduler_disabled(client, monkeypatch) -> None:
    import app.core.db as db_module
    import app.tasks.strategy_tasks as strategy_tasks

    def fail_if_called(self, db, strategy_ids=None):
        raise AssertionError("disabled scheduled task should not run strategies")

    client.put("/api/v1/preferences", json={"strategy_scheduler": {"enabled": False}})
    monkeypatch.setattr(strategy_tasks, "SessionLocal", db_module.SessionLocal)
    monkeypatch.setattr(strategy_tasks, "is_trading_time", lambda: True)
    monkeypatch.setattr(strategy_tasks.StrategyService, "run_active_strategies", fail_if_called)

    result = strategy_tasks.run_strategy_cycle_task(scheduled=True)

    assert result == {
        "status": "skipped",
        "task": "run_strategy_cycle",
        "reason": "scheduler_disabled",
        "scheduled": True,
        "strategy_ids": [],
    }


def test_run_strategy_cycle_task_skips_when_interval_not_due(client, monkeypatch) -> None:
    from datetime import datetime, timezone

    import app.core.db as db_module
    import app.tasks.strategy_tasks as strategy_tasks

    def fail_if_called(self, db, strategy_ids=None):
        raise AssertionError("scheduled task should wait until interval is due")

    client.put("/api/v1/preferences", json={"strategy_scheduler": {"interval_seconds": 900}})
    monkeypatch.setattr(strategy_tasks, "SessionLocal", db_module.SessionLocal)
    monkeypatch.setattr(strategy_tasks, "is_trading_time", lambda: True)
    monkeypatch.setattr(strategy_tasks.StrategyService, "run_active_strategies", fail_if_called)
    monkeypatch.setattr(strategy_tasks, "_last_scheduled_run_at", datetime.now(timezone.utc))

    result = strategy_tasks.run_strategy_cycle_task(scheduled=True)

    assert result["status"] == "skipped"
    assert result["reason"] == "interval_not_due"
    assert result["next_due_seconds"] > 0
