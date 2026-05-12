from datetime import date, timedelta

from sqlalchemy.orm import sessionmaker

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


def test_backtest_run_moving_average_produces_equity_curve(client, db) -> None:
    MarketDailyBarStorage(db).upsert_bars(
        [
            _bar("sh600519", date(2026, 4, 20), 10.0),
            _bar("sh600519", date(2026, 4, 21), 10.4),
            _bar("sh600519", date(2026, 4, 22), 10.9),
            _bar("sh600519", date(2026, 4, 23), 11.2),
            _bar("sh600519", date(2026, 4, 24), 11.6),
            _bar("sh600519", date(2026, 4, 25), 12.0),
            _bar("sh600519", date(2026, 4, 26), 12.5),
        ],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "max_position_pct": 1.0,
            "parameters": {"short_window": 3, "long_window": 5, "position_pct": 0.5},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["bars"] == 7
    assert payload["equity_curve"]
    assert payload["events"]
    assert payload["summary"]["strategy_name"] == "moving_average"
    assert "sharpe_ratio" in payload["summary"]["report"]
    assert "drawdown_curve" in payload["summary"]["report"]
    assert payload["final_net_worth"] > 0


def test_backtest_moving_average_enters_existing_trend(client, db) -> None:
    prices = [10.0 + index * 0.2 for index in range(80)]
    start = date(2026, 1, 1)
    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sh600519", start + timedelta(days=index), price) for index, price in enumerate(prices)],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "max_position_pct": 0.6,
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["trade_count"] > 0
    assert any(event["signal"] == "buy" for event in payload["events"])
    assert payload["trades"][0]["side"] == "buy"


def test_backtest_uses_configured_strategy_parameters(client, db) -> None:
    prices = [10.0 + index * 0.2 for index in range(80)]
    start = date(2026, 1, 1)
    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sh600519", start + timedelta(days=index), price) for index, price in enumerate(prices)],
        source="baostock",
        adjustflag="2",
    )
    strategy_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "量化策略",
            "target_type": "special_attention",
            "target_config": {},
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {
                "short_window": 5,
                "long_window": 20,
                "position_pct": 0.25,
                "volume_confirm_ratio": 0.5,
                "max_volatility_20": 0.5,
            },
        },
    )
    assert strategy_response.status_code == 200
    strategy = strategy_response.json()

    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sh600519",
            "strategy_id": strategy["id"],
            "strategy_type": "rl_trading",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "max_position_pct": 1.0,
            "parameters": {"position_pct": 0.9},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_id"] == strategy["id"]
    assert payload["strategy_name"] == "量化策略"
    assert payload["strategy_type"] == "moving_average"
    assert payload["summary"]["parameters"]["position_pct"] == 0.25
    assert payload["summary"]["parameters"]["short_window"] == 5


def test_backtest_configured_rl_model_uses_path_registry_root(client, db, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module
    import app.strategy.service as strategy_service
    import app.strategy.strategies.rl_trading as rl_trading_strategy
    import app.backtest.service as backtest_service

    model_root = tmp_path / "rl_models" / "user-1"
    monkeypatch.setattr(strategy_service.StrategyService, "_rl_model_registry_root", staticmethod(lambda user_id: model_root))
    monkeypatch.setattr(backtest_service.BacktestService, "_rl_model_registry_root", staticmethod(lambda user_id: model_root))
    monkeypatch.setattr(rl_trading_strategy, "predict_ppo_action", lambda artifact, records: {"action_type": "buy", "target_position_pct": 0.2})

    registry = training_module.RLModelRegistry(model_root)
    registry.save({
        "model_id": "trained-model",
        "name": "已训练模型",
        "status": "validated",
        "algorithm": "ppo_trading",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "scope": "manual",
        "symbols": [],
        "config": {},
        "training": {"policy_path": "policy.zip"},
        "metrics": {"trade_count": 1},
        "validation": {"passed": True, "blockers": [], "warnings": []},
        "evaluations": [],
        "dataset_manifest": {},
    })
    start = date(2026, 1, 1)
    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sh600519", start + timedelta(days=index), 10 + index * 0.1) for index in range(40)],
        source="baostock",
        adjustflag="2",
    )
    strategy_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "训练模型策略",
            "target_type": "special_attention",
            "target_config": {},
            "strategy_type": "rl_trading",
            "execution_mode": "signal_only",
            "parameters": {
                "rl_policy_mode": "trained_model",
                "model_id": "trained-model",
                "ma_short_window": 5,
                "ma_long_window": 20,
                "max_position_pct": 0.5,
                "min_confidence": 0,
            },
        },
    )
    assert strategy_response.status_code == 200

    response = client.post(
        "/api/v1/backtest/run",
        json={"symbol": "sh600519", "strategy_id": strategy_response.json()["id"], "initial_cash": 100000.0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_name"] == "训练模型策略"
    assert "model_registry_root" not in payload["summary"]["parameters"]
    assert any(event["signal"] == "buy" for event in payload["events"])


def test_backtest_jobs_are_scoped_to_current_user(client, tmp_path, monkeypatch) -> None:
    import app.api.backtest as backtest_api
    import app.backtest.jobs as backtest_jobs

    registry = backtest_jobs.BacktestJobRegistry(root=tmp_path / "backtest_jobs")
    monkeypatch.setattr(backtest_api, "job_registry", registry)

    first = registry.submit({"symbol": "sh600519", "user_id": 1, "tenant_id": "local"})
    second = registry.submit({"symbol": "sh601318", "user_id": 2, "tenant_id": "local"})

    own_job = client.get(f"/api/v1/backtest/jobs/{first['job_id']}")
    other_job = client.get(f"/api/v1/backtest/jobs/{second['job_id']}")
    latest_job = client.get("/api/v1/backtest/jobs/latest")

    assert own_job.status_code == 200
    assert own_job.json()["payload"]["user_id"] == 1
    assert other_job.status_code == 404
    assert latest_job.status_code == 404


def test_backtest_rl_baseline_generates_trades_for_experiment(client, db) -> None:
    prices = [10.0 + index * 0.15 for index in range(80)]
    start = date(2025, 1, 1)
    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sz002920", start + timedelta(days=index), price) for index, price in enumerate(prices)],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sz002920",
            "strategy_type": "rl_trading",
            "start_date": "2025-01-01",
            "end_date": "2026-05-11",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "max_position_pct": 0.6,
            "parameters": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["strategy_type"] == "rl_trading"
    assert payload["trade_count"] > 0
    assert any(event["signal"] == "buy" for event in payload["events"])
    assert payload["trades"][0]["side"] == "buy"


def test_backtest_rl_threshold_zero_is_respected(client, db) -> None:
    prices = [10.0 + index * 0.01 for index in range(80)]
    start = date(2025, 1, 1)
    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sz002920", start + timedelta(days=index), price) for index, price in enumerate(prices)],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sz002920",
            "strategy_type": "rl_trading",
            "start_date": "2025-01-01",
            "end_date": "2026-05-11",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "max_position_pct": 0.6,
            "parameters": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trade_count"] > 0
    assert any(event["signal"] == "buy" for event in payload["events"])


def test_backtest_zero_trade_diagnostics_explain_hold_signals(client, db) -> None:
    prices = [10.0 for _ in range(80)]
    start = date(2025, 1, 1)
    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sz002920", start + timedelta(days=index), price) for index, price in enumerate(prices)],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sz002920",
            "strategy_type": "rl_trading",
            "start_date": "2025-01-01",
            "end_date": "2026-05-11",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "max_position_pct": 0.6,
            "parameters": {
                "rl_policy_mode": "baseline",
                "baseline_buy_trend_threshold": 1,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    diagnostics = payload["summary"]["diagnostics"]
    assert payload["trade_count"] == 0
    assert diagnostics["zero_trade"] is True
    assert diagnostics["signal_counts"]["hold"] > 0
    assert diagnostics["no_trade_reason_counts"]["model_hold_or_zero_target"] > 0
    assert diagnostics["no_trade_samples"]


def test_backtest_auto_syncs_missing_baostock_history(client, db, monkeypatch) -> None:
    import app.backtest.service as backtest_service

    class StubSyncService:
        def __init__(self, sync_db) -> None:
            self.sync_db = sync_db

        def sync_history(self, *, symbols, start_date, end_date, adjustflag, incremental):
            MarketDailyBarStorage(self.sync_db).upsert_bars(
                [_bar(symbols[0], start_date + timedelta(days=index), 10.0 + index * 0.2) for index in range(80)],
                source="baostock",
                adjustflag=adjustflag,
            )

            class Result:
                def to_dict(self):
                    return {
                        "status": "completed",
                        "source": "baostock",
                        "adjustflag": adjustflag,
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "requested_symbols": symbols,
                        "incremental": incremental,
                        "resolved_ranges": [],
                        "succeeded_symbols": symbols,
                        "success_count": 1,
                        "failure_count": 0,
                        "failures": [],
                        "bars_upserted": 80,
                    }

            return Result()

    monkeypatch.setattr(backtest_service, "BaoStockHistorySyncService", StubSyncService)

    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sz002920",
            "strategy_type": "rl_trading",
            "start_date": "2025-01-01",
            "end_date": "2026-05-11",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "max_position_pct": 0.6,
            "parameters": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["bars"] == 80
    assert payload["trade_count"] > 0
    assert payload["summary"]["history_sync"]["attempted"] is True
    assert payload["summary"]["history_sync"]["bars_upserted"] == 80


def test_backtest_empty_explains_sync_failure(client, monkeypatch) -> None:
    import app.backtest.service as backtest_service

    class FailingSyncService:
        def __init__(self, sync_db) -> None:
            self.sync_db = sync_db

        def sync_history(self, **kwargs):
            raise RuntimeError("baostock unavailable")

    monkeypatch.setattr(backtest_service, "BaoStockHistorySyncService", FailingSyncService)

    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sz002920",
            "strategy_type": "rl_trading",
            "start_date": "2025-01-01",
            "end_date": "2026-05-11",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "empty"
    assert payload["bars"] == 0
    assert payload["summary"]["reason"] == "no_records_after_sync"
    assert payload["summary"]["history_sync"]["attempted"] is True
    assert payload["summary"]["history_sync"]["status"] == "failed"
    assert payload["summary"]["history_sync"]["error"] == "baostock unavailable"


def test_backtest_uses_fallback_provider_when_baostock_returns_no_bars(client, db, monkeypatch) -> None:
    import app.backtest.service as backtest_service

    class FailedSyncService:
        def __init__(self, sync_db) -> None:
            self.sync_db = sync_db

        def sync_history(self, *, symbols, start_date, end_date, adjustflag, incremental):
            class Result:
                def to_dict(self):
                    return {
                        "status": "failed",
                        "source": "baostock",
                        "adjustflag": adjustflag,
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "requested_symbols": symbols,
                        "incremental": incremental,
                        "resolved_ranges": [],
                        "succeeded_symbols": [],
                        "success_count": 0,
                        "failure_count": 1,
                        "failures": [{"symbol": symbols[0], "reason": "baostock login failed"}],
                        "bars_upserted": 0,
                    }

            return Result()

    class FallbackMarketDataService:
        def get_daily_bars_with_source(self, symbol, limit, force_refresh=False, source=None):
            class Payload:
                source = "eastmoney"
                bars = [_bar(symbol, date(2025, 1, 1) + timedelta(days=index), 10.0 + index * 0.2) for index in range(80)]

            return Payload()

    monkeypatch.setattr(backtest_service, "BaoStockHistorySyncService", FailedSyncService)
    monkeypatch.setattr(backtest_service, "MarketDataService", FallbackMarketDataService)

    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sz002920",
            "strategy_type": "rl_trading",
            "start_date": "2025-01-01",
            "end_date": "2026-05-11",
            "parameters": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["bars"] == 80
    assert payload["summary"]["history_sync"]["status"] == "fallback_success"
    assert payload["summary"]["history_sync"]["fallback_source"] == "eastmoney"
    assert payload["summary"]["history_sync"]["primary_sync"]["status"] == "failed"


def test_backtest_job_submission_and_status(client, db, monkeypatch, tmp_path) -> None:
    import app.api.backtest as backtest_api
    import app.backtest.jobs as backtest_jobs

    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sh600519", date(2026, 4, 20) + timedelta(days=index), 10.0 + index * 0.2) for index in range(30)],
        source="baostock",
        adjustflag="2",
    )
    db.commit()
    registry = backtest_jobs.BacktestJobRegistry(tmp_path / "backtest_jobs")

    class InlineExecutor:
        def submit(self, fn, *args, **kwargs):
            fn(*args, **kwargs)

    monkeypatch.setattr(backtest_jobs.BacktestJobRegistry, "_executor", InlineExecutor())
    monkeypatch.setattr(backtest_api, "job_registry", registry)
    monkeypatch.setattr(backtest_jobs, "SessionLocal", sessionmaker(bind=db.get_bind()))

    response = client.post(
        "/api/v1/backtest/jobs",
        json={
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "start_date": "2026-04-20",
            "end_date": "2026-05-20",
            "parameters": {"short_window": 3, "long_window": 5, "position_pct": 0.5},
        },
    )

    assert response.status_code == 200
    submitted = response.json()
    assert submitted["job_id"].startswith("backtest-")

    status_response = client.get(f"/api/v1/backtest/jobs/{submitted['job_id']}")

    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] == "succeeded"
    assert payload["progress_pct"] == 100.0
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["bars"] > 0


def test_backtest_run_empty_data_is_explainable(client) -> None:
    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "sh600519",
            "strategy_type": "macd",
            "source": "manual",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "empty"
    assert payload["summary"]["reason"] == "no_records"
    assert payload["summary"]["history_sync"]["attempted"] is False


def test_backtest_jobs_are_scoped_to_current_user(client, tmp_path, monkeypatch) -> None:
    import app.api.backtest as backtest_api
    import app.backtest.jobs as backtest_jobs

    registry = backtest_jobs.BacktestJobRegistry(root=tmp_path / "backtest_jobs")
    monkeypatch.setattr(backtest_api, "job_registry", registry)
    monkeypatch.setattr(backtest_jobs.BacktestJobRegistry._executor, "submit", lambda *args, **kwargs: None)

    own_job = registry.submit({"symbol": "sh600519", "user_id": 1, "tenant_id": "local"})
    other_job = registry.submit({"symbol": "sh601318", "user_id": 2, "tenant_id": "local"})

    own_response = client.get(f"/api/v1/backtest/jobs/{own_job['job_id']}")
    other_response = client.get(f"/api/v1/backtest/jobs/{other_job['job_id']}")
    latest_response = client.get("/api/v1/backtest/jobs/latest")

    assert own_response.status_code == 200
    assert own_response.json()["payload"]["user_id"] == 1
    assert other_response.status_code == 404
    assert latest_response.status_code == 200
    assert latest_response.json()["payload"]["user_id"] == 1
    assert latest_response.json()["job_id"] == own_job["job_id"]


def test_backtest_daily_review_returns_report_sections(client, db) -> None:
    MarketDailyBarStorage(db).upsert_bars(
        [
            _bar("sh600519", date(2026, 4, 20), 10.0),
            _bar("sh600519", date(2026, 4, 21), 10.4),
            _bar("sh600519", date(2026, 4, 22), 10.9),
            _bar("sh600519", date(2026, 4, 23), 11.2),
            _bar("sh600519", date(2026, 4, 24), 11.6),
            _bar("sh600519", date(2026, 4, 25), 12.0),
            _bar("sh600519", date(2026, 4, 26), 12.5),
        ],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/backtest/daily-review",
        json={
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "parameters": {"short_window": 3, "long_window": 5, "position_pct": 0.5},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["headline"]
    assert payload["highlights"]
    assert payload["risks"]
    assert payload["next_actions"]
    assert payload["backtest"]["summary"]["report"]["annualized_return_pct"] is not None
