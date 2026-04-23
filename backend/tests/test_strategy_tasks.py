from app.core.celery_app import celery_app
from app.tasks.strategy_tasks import run_strategy_cycle


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


def test_run_strategy_cycle_wrapper_uses_task_result(client, monkeypatch) -> None:
    import app.tasks.strategy_tasks as strategy_tasks

    monkeypatch.setattr(
        strategy_tasks,
        "run_strategy_cycle_task",
        lambda strategy_ids=None: {
            "status": "completed",
            "task": "run_strategy_cycle",
            "count": len(strategy_ids or []),
            "strategy_ids": strategy_ids or [],
            "results": [],
        },
    )

    result = run_strategy_cycle()

    assert result["status"] == "completed"
    assert result["task"] == "run_strategy_cycle"
    assert result["count"] == 0


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
