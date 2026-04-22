from app.tasks.trading_tasks import match_pending_orders_task


def test_match_pending_orders_task_runs(client, monkeypatch) -> None:
    import app.tasks.trading_tasks as trading_tasks

    monkeypatch.setattr(trading_tasks.TradingService, "match_pending_orders", lambda self, db: {"status": "accepted", "matched_count": 0, "matched_orders": []})

    result = match_pending_orders_task()

    assert result["status"] == "accepted"
    assert result["matched_count"] == 0
