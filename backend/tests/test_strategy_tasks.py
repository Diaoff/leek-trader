import logging

from app.core.celery_app import celery_app


def test_run_strategy_cycle_task_executes_active_strategies(client, monkeypatch) -> None:
    import app.core.db as db_module
    import app.tasks.strategy_tasks as strategy_tasks

    monkeypatch.setattr(strategy_tasks, "SessionLocal", db_module.SessionLocal)

    result = strategy_tasks.run_strategy_cycle_task()

    assert result["status"] == "completed"
    assert result["task"] == "run_strategy_cycle"
    assert result["count"] == 2
    assert len(result["strategy_ids"]) == 2
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


def test_strategy_task_uses_retry_policy_and_logs_success(client, monkeypatch, caplog) -> None:
    import app.core.db as db_module
    import app.tasks.strategy_tasks as strategy_tasks

    monkeypatch.setattr(strategy_tasks, "SessionLocal", db_module.SessionLocal)

    with caplog.at_level(logging.INFO):
        result = strategy_tasks.run_strategy_cycle_task([])

    assert result["count"] == 0
    assert strategy_tasks.run_strategy_cycle_task.autoretry_for == (Exception,)
    assert strategy_tasks.run_strategy_cycle_task.retry_backoff is True
    assert strategy_tasks.run_strategy_cycle_task.retry_kwargs["max_retries"] == 3
    assert "Celery task started task=app.tasks.strategy_tasks.run_strategy_cycle_task" in caplog.text
    assert "Celery task succeeded task=app.tasks.strategy_tasks.run_strategy_cycle_task" in caplog.text
