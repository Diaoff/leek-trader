from datetime import date, timedelta
import time

from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot


def _bar(symbol: str, trade_date: date, close_price: float) -> DailyBarSnapshot:
    return DailyBarSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        open_price=close_price * 0.99,
        close_price=close_price,
        high_price=close_price * 1.01,
        low_price=close_price * 0.98,
        volume=1000000.0,
        turnover=12000000.0,
    )


def _seed_bars(db) -> None:
    start = date(2025, 1, 1)
    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sh600519", start + timedelta(days=index), 10.0 + index * 0.1) for index in range(220)],
        source="baostock",
        adjustflag="2",
    )


def test_backtest_optimization_generates_ranked_candidates(client, db) -> None:
    _seed_bars(db)

    response = client.post(
        "/api/v1/backtest/optimizations/jobs",
        json={
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "start_date": "2025-01-01",
            "end_date": "2025-06-30",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "fixed_slippage_amount": 0.02,
            "parameters": {"long_window": 20},
            "parameter_grid": {"short_window": [3, 5], "position_pct": [0.1, 0.2]},
            "target_metric": "total_return_pct",
            "sort_direction": "desc",
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    payload = client.get(f"/api/v1/backtest/optimizations/jobs/{job_id}").json()
    assert payload["status"] in {"queued", "running", "succeeded"}


def test_backtest_optimization_rejects_oversized_grid(client) -> None:
    response = client.post(
        "/api/v1/backtest/optimizations/jobs",
        json={
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "parameter_grid": {"short_window": list(range(31))},
        },
    )

    assert response.status_code == 422


def test_backtest_optimization_service_out_of_sample_history(client, db, tmp_path, monkeypatch) -> None:
    import app.api.backtest as backtest_api
    import app.backtest.jobs as backtest_jobs
    import app.backtest.service as backtest_service

    _seed_bars(db)
    monkeypatch.setattr(backtest_service.BacktestService, "_sync_missing_history", staticmethod(lambda *args, **kwargs: {"attempted": False, "reason": "test"}))
    registry = backtest_jobs.BacktestJobRegistry(root=tmp_path / "optimization_jobs", prefix="backtest-optimization", job_kind="optimization")
    monkeypatch.setattr(backtest_api, "optimization_job_registry", registry)

    response = client.post(
        "/api/v1/backtest/optimizations/jobs",
        json={
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "start_date": "2025-01-01",
            "end_date": "2025-05-31",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "parameters": {"long_window": 20},
            "parameter_grid": {"short_window": [3, 5], "position_pct": [0.1, 0.2]},
            "target_metric": "total_return_pct",
            "out_of_sample": {"start_date": "2025-06-01", "end_date": "2025-08-08"},
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    for _ in range(60):
        job = client.get(f"/api/v1/backtest/optimizations/jobs/{job_id}").json()
        if job["status"] == "succeeded":
            break
        time.sleep(0.05)
    assert job["status"] == "succeeded"
    result = job["result"]
    assert result["combinations"] == 4
    assert result["best_candidate"]
    assert result["out_of_sample"]

    history = client.get("/api/v1/backtest/optimizations/history")
    assert history.status_code == 200
    items = history.json()
    assert items
    assert items[0]["job_id"] == job_id
    assert items[0]["best_parameters"]
