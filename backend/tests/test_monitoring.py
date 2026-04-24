def test_async_task_summary_exposes_retry_policy_and_stats(client, monkeypatch) -> None:
    import app.api.monitoring as monitoring_api
    from app.core.config import settings

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
    assert market_task["stats"]["failed"] == 1
    assert payload["note"] == "任务统计为当前进程内基线数据，重启 worker 后会重置。"


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
