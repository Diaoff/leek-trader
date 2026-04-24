import logging


def test_async_task_summary_exposes_retry_policy_and_stats(client, monkeypatch) -> None:
    import app.api.monitoring as monitoring_api
    from app.core.config import settings

    monkeypatch.setattr(
        monitoring_api,
        "get_persisted_task_stats",
        lambda: {},
    )
    monkeypatch.setattr(
        monitoring_api,
        "get_task_runtime_stats",
        lambda: {
            "app.tasks.market_tasks.refresh_market_quotes_task": {
                "task_name": "app.tasks.market_tasks.refresh_market_quotes_task",
                "started": 2,
                "succeeded": 2,
                "failed": 1,
                "retried": 1,
                "last_task_id": "market-1",
                "last_started_at": "2026-04-24T00:00:00+00:00",
                "last_succeeded_at": "2026-04-24T00:01:00+00:00",
                "last_failed_at": "2026-04-24T00:02:00+00:00",
                "last_retried_at": "2026-04-24T00:02:30+00:00",
                "last_error": "provider timeout",
                "last_retry_error": "provider timeout",
            }
        },
    )

    response = client.get("/api/v1/monitoring/async-tasks/summary")

    assert response.status_code == 200
    payload = response.json()
    market_task = next(item for item in payload["tasks"] if item["key"] == "refresh_market_quotes")

    assert market_task["schedule_seconds"] == float(settings.market_refresh_interval_seconds)
    assert market_task["retry_policy"]["max_retries"] == 3
    assert market_task["retry_policy"]["retry_backoff"] is True
    assert market_task["stats_source"] == "process"
    assert market_task["stats"]["failed"] == 1
    assert payload["note"] == "任务统计优先读取数据库持久化结果；未落库任务回退为当前 worker 进程内基线数据。"


def test_async_task_summary_prefers_persisted_stats(client, monkeypatch) -> None:
    import app.api.monitoring as monitoring_api

    monkeypatch.setattr(
        monitoring_api,
        "get_persisted_task_stats",
        lambda: {
            "app.tasks.market_tasks.refresh_market_quotes_task": {
                "task_name": "app.tasks.market_tasks.refresh_market_quotes_task",
                "started": 4,
                "succeeded": 3,
                "failed": 1,
                "retried": 2,
                "last_task_id": "db-task-1",
                "last_started_at": "2026-04-24T00:00:00+00:00",
                "last_succeeded_at": "2026-04-24T00:01:00+00:00",
                "last_failed_at": "2026-04-24T00:02:00+00:00",
                "last_retried_at": "2026-04-24T00:02:30+00:00",
                "last_error": "provider timeout",
                "last_retry_error": "provider timeout",
            }
        },
    )
    monkeypatch.setattr(
        monitoring_api,
        "get_task_runtime_stats",
        lambda: {
            "app.tasks.market_tasks.refresh_market_quotes_task": {
                "task_name": "app.tasks.market_tasks.refresh_market_quotes_task",
                "started": 1,
                "succeeded": 1,
                "failed": 0,
                "retried": 0,
                "last_task_id": "runtime-task-1",
                "last_started_at": "2026-04-24T00:10:00+00:00",
                "last_succeeded_at": "2026-04-24T00:10:10+00:00",
                "last_failed_at": None,
                "last_retried_at": None,
                "last_error": None,
                "last_retry_error": None,
            }
        },
    )

    response = client.get("/api/v1/monitoring/async-tasks/summary")

    assert response.status_code == 200
    payload = response.json()
    market_task = next(item for item in payload["tasks"] if item["key"] == "refresh_market_quotes")

    assert market_task["stats_source"] == "database"
    assert market_task["stats"]["started"] == 4
    assert market_task["stats"]["last_task_id"] == "db-task-1"


def test_dispatch_refresh_market_quotes_enqueues_task(client, monkeypatch) -> None:
    import app.api.monitoring as monitoring_api

    calls: dict[str, object] = {}

    class DummyResult:
        id = "task-refresh-1"

    def fake_apply_async(*, kwargs=None):
        calls["kwargs"] = kwargs
        return DummyResult()

    monkeypatch.setattr(monitoring_api.refresh_market_quotes_task, "apply_async", fake_apply_async)

    response = client.post(
        "/api/v1/monitoring/async-tasks/refresh-market-quotes",
        json={"symbols": ["sh600519", "sz000001"]},
    )

    assert response.status_code == 200
    assert calls["kwargs"] == {"symbols": ["sh600519", "sz000001"]}
    assert response.json() == {
        "status": "queued",
        "task": "refresh_market_quotes",
        "task_name": "app.tasks.market_tasks.refresh_market_quotes_task",
        "task_id": "task-refresh-1",
        "symbols": ["sh600519", "sz000001"],
    }


def test_dispatch_match_pending_orders_enqueues_task(client, monkeypatch) -> None:
    import app.api.monitoring as monitoring_api

    calls: dict[str, int] = {"count": 0}

    class DummyResult:
        id = "task-match-1"

    def fake_apply_async():
        calls["count"] += 1
        return DummyResult()

    monkeypatch.setattr(monitoring_api.match_pending_orders_task, "apply_async", fake_apply_async)

    response = client.post("/api/v1/monitoring/async-tasks/match-pending-orders")

    assert response.status_code == 200
    assert calls["count"] == 1
    assert response.json() == {
        "status": "queued",
        "task": "match_pending_orders",
        "task_name": "app.tasks.trading_tasks.match_pending_orders_task",
        "task_id": "task-match-1",
    }


def test_persisted_task_stats_and_alert_log(client, caplog) -> None:
    import app.core.celery_app as celery_app_module
    import app.core.db as db_module

    task_name = "app.tasks.market_tasks.refresh_market_quotes_task"
    task_id = "persisted-market-task"

    celery_app_module.SessionLocal = db_module.SessionLocal
    celery_app_module.engine = db_module.engine
    celery_app_module._persistence_schema_ready = False

    celery_app_module._persist_task_event(task_name, "started", task_id=task_id)
    celery_app_module._persist_task_event(task_name, "retried", task_id=task_id, error=RuntimeError("provider timeout"))
    celery_app_module._persist_task_event(task_name, "failed", task_id=task_id, error=RuntimeError("provider timeout"))

    stats = celery_app_module.get_persisted_task_stats()[task_name]

    assert stats["started"] >= 1
    assert stats["failed"] >= 1
    assert stats["retried"] >= 1
    assert stats["last_error"] == "provider timeout"
    assert stats["last_retry_error"] == "provider timeout"

    with caplog.at_level(logging.ERROR):
        celery_app_module._emit_async_task_alert(task_name, task_id, RuntimeError("provider timeout"))

    assert "ASYNC_TASK_ALERT task=app.tasks.market_tasks.refresh_market_quotes_task task_id=persisted-market-task error=provider timeout" in caplog.text
