from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app.market.provider_health import provider_health_tracker
from app.market.source_health import MarketSourceHealthService
from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot
from app.backtest.service import BacktestService
from app.trading.execution import calculate_execution_cost
from app.trading.service import TradingService


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


class TargetPositionPlugin:
    name = "target_position_test"

    def __init__(self, target_by_index: list[tuple[str, float]]) -> None:
        self.target_by_index = target_by_index

    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> dict[str, object]:
        action, target_pct = self.target_by_index[min(len(bars) - 1, len(self.target_by_index) - 1)]
        return {
            "symbol": symbol,
            "strategy": self.name,
            "signal": action,
            "position_pct": target_pct,
            "trigger_reason": f"test_{action}",
        }


def _simulate_with_plugin(
    bars: list[DailyBarSnapshot],
    plugin: TargetPositionPlugin,
    parameters: dict | None = None,
    *,
    initial_cash: float = 100000.0,
    commission_rate: float = 0.0,
    min_commission: float = 5.0,
    stamp_tax_rate: float = 0.0005,
) -> dict[str, object]:
    return BacktestService()._simulate_events(
        bars=bars,
        plugin_name=plugin.name,
        plugin=plugin,
        parameters=parameters or {},
        initial_cash=initial_cash,
        commission_rate=commission_rate,
        min_commission=min_commission,
        stamp_tax_rate=stamp_tax_rate,
        slippage_rate=0.0,
        max_position_pct=1.0,
        source="unit-test",
        adjustflag="2",
    )


@pytest.fixture(autouse=True)
def reset_backtest_provider_health():
    provider_health_tracker.reset()
    yield
    provider_health_tracker.reset()


def test_backtest_rounds_trades_to_a_share_lots() -> None:
    bars = [_bar("sh600519", date(2026, 4, 20), 30.0)]
    plugin = TargetPositionPlugin([("buy", 0.1)])

    result = _simulate_with_plugin(bars, plugin)

    assert result["trades"][0]["shares_delta"] == 300


def test_backtest_blocks_same_day_sell_for_t_plus_one() -> None:
    bars = [
        _bar("sh600519", date(2026, 4, 20), 10.0),
        _bar("sh600519", date(2026, 4, 20), 10.2),
        _bar("sh600519", date(2026, 4, 21), 10.4),
    ]
    plugin = TargetPositionPlugin([("buy", 0.5), ("sell", 0.0), ("sell", 0.0)])

    result = _simulate_with_plugin(bars, plugin)

    assert [trade["side"] for trade in result["trades"]] == ["buy", "sell"]
    assert result["events"][1]["no_trade_reason"] == "t_plus_one_sell_blocked"
    assert result["events"][1]["shares_delta"] == 0


def test_backtest_blocks_suspended_and_limit_trades() -> None:
    suspended = _bar("sh600519", date(2026, 4, 20), 10.0)
    suspended.trade_status = 0
    abnormal_status = _bar("sh600519", date(2026, 4, 20), 10.0)
    abnormal_status.trade_status = 2
    limit_up = _bar("sh600519", date(2026, 4, 21), 11.0)
    limit_up.preclose = 10.0
    normal_buy = _bar("sh600519", date(2026, 4, 22), 10.5)
    normal_buy.preclose = 11.0
    limit_down = _bar("sh600519", date(2026, 4, 23), 9.45)
    limit_down.preclose = 10.5
    normal_sell = _bar("sh600519", date(2026, 4, 24), 9.7)
    normal_sell.preclose = 9.45
    plugin = TargetPositionPlugin([("buy", 0.5), ("buy", 0.5), ("buy", 0.5), ("buy", 0.5), ("sell", 0.0), ("sell", 0.0)])

    result = _simulate_with_plugin([suspended, abnormal_status, limit_up, normal_buy, limit_down, normal_sell], plugin)

    assert result["events"][0]["no_trade_reason"] == "suspended"
    assert result["events"][1]["no_trade_reason"] == "suspended"
    assert result["events"][2]["no_trade_reason"] == "limit_up_buy_blocked"
    assert result["events"][4]["no_trade_reason"] == "limit_down_sell_blocked"
    assert [trade["side"] for trade in result["trades"]] == ["buy", "sell"]


def test_backtest_uses_st_five_percent_price_limits() -> None:
    st_limit_up = _bar("sh600519", date(2026, 4, 20), 10.5)
    st_limit_up.preclose = 10.0
    st_limit_up.is_st = True
    st_limit_down = _bar("sh600519", date(2026, 4, 22), 9.5)
    st_limit_down.preclose = 10.0
    st_limit_down.is_st = True
    regular_five_percent_up = _bar("sh600519", date(2026, 4, 20), 10.5)
    regular_five_percent_up.preclose = 10.0
    regular_five_percent_up.is_st = False
    normal_buy = _bar("sh600519", date(2026, 4, 21), 10.0)
    normal_buy.preclose = 10.0
    plugin = TargetPositionPlugin([("buy", 0.5), ("sell", 0.0)])

    st_buy_result = _simulate_with_plugin([st_limit_up], TargetPositionPlugin([("buy", 0.5)]))
    st_sell_result = _simulate_with_plugin([normal_buy, st_limit_down], plugin)
    regular_result = _simulate_with_plugin([regular_five_percent_up], TargetPositionPlugin([("buy", 0.5)]))

    assert st_buy_result["events"][0]["no_trade_reason"] == "limit_up_buy_blocked"
    assert st_sell_result["events"][1]["no_trade_reason"] == "limit_down_sell_blocked"
    assert regular_result["trades"][0]["side"] == "buy"


def test_backtest_applies_volume_capacity_and_records_unfilled_shares() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    bar.volume = 1000.0
    plugin = TargetPositionPlugin([("buy", 1.0)])

    result = _simulate_with_plugin([bar], plugin, parameters={"max_volume_participation": 0.2})

    assert result["trades"][0]["requested_shares_delta"] == 10000
    assert result["trades"][0]["shares_delta"] == 200
    assert result["trades"][0]["unfilled_shares"] == 9800
    assert result["trades"][0]["execution"]["mode"] == "backtest"
    assert result["trades"][0]["execution"]["requested_quantity"] == 10000
    assert result["trades"][0]["execution"]["filled_quantity"] == 200
    assert result["trades"][0]["execution"]["unfilled_quantity"] == 9800
    assert result["trades"][0]["execution"]["rejection_code"] is None
    assert result["summary"]["total_unfilled_shares"] == 9800
    assert result["summary"]["execution_model"]["max_volume_participation"] == 0.2
    assert result["summary"]["execution_model"]["limit_move_policy"] == {"buy": "reject", "sell": "reject"}


def test_backtest_applies_impact_slippage_cost() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    bar.volume = 1000.0
    plugin = TargetPositionPlugin([("buy", 1.0)])

    result = _simulate_with_plugin([bar], plugin, parameters={"max_volume_participation": 0.2, "impact_slippage_factor": 0.1})

    assert result["trades"][0]["shares_delta"] == 200
    assert result["trades"][0]["execution_price"] == 10.2
    assert result["summary"]["total_slippage_cost"] == 40.0
    assert result["summary"]["execution_model"]["impact_slippage_factor"] == 0.1


def test_backtest_applies_fixed_slippage_and_reports_execution_model() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    plugin = TargetPositionPlugin([("buy", 0.1)])

    result = BacktestService()._simulate_events(
        bars=[bar],
        plugin_name=plugin.name,
        plugin=plugin,
        parameters={"fixed_slippage_amount": 0.05},
        initial_cash=100000.0,
        commission_rate=0.0,
        min_commission=5.0,
        stamp_tax_rate=0.0005,
        slippage_rate=0.0,
        fixed_slippage_amount=0.05,
        max_position_pct=1.0,
        source="unit-test",
        adjustflag="2",
    )

    assert result["trades"][0]["execution_price"] == 10.05
    assert result["summary"]["total_slippage_cost"] == 45.0
    assert result["summary"]["execution_model"]["slippage_rate"] == 0.0
    assert result["summary"]["execution_model"]["fixed_slippage_amount"] == 0.05
    assert "固定滑点" in result["summary"]["research_report"]["content"]


def test_backtest_stacks_ratio_fixed_and_impact_slippage_in_order() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    bar.volume = 1000.0
    plugin = TargetPositionPlugin([("buy", 1.0)])

    result = BacktestService()._simulate_events(
        bars=[bar],
        plugin_name=plugin.name,
        plugin=plugin,
        parameters={"max_volume_participation": 0.2, "impact_slippage_factor": 0.1, "fixed_slippage_amount": 0.05},
        initial_cash=100000.0,
        commission_rate=0.0,
        min_commission=5.0,
        stamp_tax_rate=0.0005,
        slippage_rate=0.01,
        fixed_slippage_amount=0.05,
        max_position_pct=1.0,
        source="unit-test",
        adjustflag="2",
    )

    assert result["trades"][0]["shares_delta"] == 200
    assert result["trades"][0]["execution_price"] == 10.353
    assert result["summary"]["execution_model"]["slippage_rate"] == 0.01
    assert result["summary"]["execution_model"]["fixed_slippage_amount"] == 0.05
    assert result["summary"]["execution_model"]["impact_slippage_factor"] == 0.1


def test_backtest_recaps_buy_affordability_after_impact_slippage() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    plugin = TargetPositionPlugin([("buy", 1.0)])

    result = _simulate_with_plugin([bar], plugin, parameters={"impact_slippage_factor": 0.1})

    assert result["equity_curve"][0]["cash"] >= 0
    assert result["trades"][0]["shares_delta"] == 9900
    assert result["trades"][0]["unfilled_shares"] == 100
    assert result["trades"][0]["execution_price"] == 10.0099


def test_backtest_buy_fee_matches_shared_paper_trading_cost(db) -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 100.0)
    result = _simulate_with_plugin(
        [bar],
        TargetPositionPlugin([("buy", 0.1)]),
        commission_rate=0.001,
        min_commission=5.0,
        stamp_tax_rate=0.002,
    )

    trade = result["trades"][0]
    shared_cost = calculate_execution_cost(
        quantity=trade["shares_delta"],
        price=trade["execution_price"],
        side="buy",
        commission_rate=0.001,
        min_commission=5.0,
        stamp_tax_rate=0.002,
    )
    service = TradingService()
    service.preference_service.trading_preferences = lambda **kwargs: SimpleNamespace(
        commission_rate=0.001,
        min_commission=5.0,
        stamp_tax_rate=0.002,
    )
    paper_fee = service._calculate_trade_fee(
        db,
        trade_value=shared_cost.trade_value,
        side="buy",
        user_id=None,
    )

    assert trade["fee"] == float(shared_cost.total_fee)
    assert float(paper_fee) == float(shared_cost.total_fee)


def test_backtest_sell_fee_matches_shared_paper_trading_cost(db) -> None:
    bars = [
        _bar("sh600519", date(2026, 4, 20), 100.0),
        _bar("sh600519", date(2026, 4, 21), 110.0),
    ]
    result = _simulate_with_plugin(
        bars,
        TargetPositionPlugin([("buy", 0.2), ("sell", 0.0)]),
        commission_rate=0.001,
        min_commission=5.0,
        stamp_tax_rate=0.002,
    )

    trade = result["trades"][1]
    shared_cost = calculate_execution_cost(
        quantity=abs(trade["shares_delta"]),
        price=trade["execution_price"],
        side="sell",
        commission_rate=0.001,
        min_commission=5.0,
        stamp_tax_rate=0.002,
    )
    service = TradingService()
    service.preference_service.trading_preferences = lambda **kwargs: SimpleNamespace(
        commission_rate=0.001,
        min_commission=5.0,
        stamp_tax_rate=0.002,
    )
    paper_fee = service._calculate_trade_fee(
        db,
        trade_value=shared_cost.trade_value,
        side="sell",
        user_id=None,
    )

    assert trade["fee"] == float(shared_cost.total_fee)
    assert float(paper_fee) == float(shared_cost.total_fee)


def test_backtest_respects_min_commission_when_buying_affordable_lots() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    result = _simulate_with_plugin(
        [bar],
        TargetPositionPlugin([("buy", 1.0)]),
        initial_cash=1004.0,
        commission_rate=0.0003,
        min_commission=5.0,
    )

    assert result["trades"] == []
    assert result["events"][0]["shares_delta"] == 0
    assert result["events"][0]["no_trade_reason"] == "insufficient_cash_or_lot"
    assert result["events"][0]["rejection_code"] == "insufficient_cash_or_lot"


def test_backtest_min_commission_can_reduce_bought_shares_without_overspending() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    result = _simulate_with_plugin(
        [bar],
        TargetPositionPlugin([("buy", 1.0)]),
        initial_cash=1006.0,
        commission_rate=0.0003,
        min_commission=5.0,
    )

    assert result["trades"][0]["shares_delta"] == 100
    assert result["equity_curve"][0]["cash"] == 1.0


def test_backtest_no_trade_reason_and_rejection_code_share_standard_code() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    result = _simulate_with_plugin([bar], TargetPositionPlugin([("hold", 0.5)]))

    assert result["events"][0]["no_trade_reason"] == "hold_signal"
    assert result["events"][0]["rejection_code"] == "hold_signal"


def test_backtest_model_hold_reason_uses_standard_code_in_both_fields() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    result = _simulate_with_plugin([bar], TargetPositionPlugin([("hold", 0.0)]))

    assert result["events"][0]["no_trade_reason"] == "model_hold_or_zero_target"
    assert result["events"][0]["rejection_code"] == "model_hold_or_zero_target"


def test_backtest_target_delta_too_small_uses_standard_code_in_both_fields() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    result = _simulate_with_plugin([bar], TargetPositionPlugin([("buy", 0.00009)]))

    assert result["events"][0]["no_trade_reason"] == "target_delta_too_small"
    assert result["events"][0]["rejection_code"] == "target_delta_too_small"


def test_backtest_limit_move_policy_is_reported_in_summary() -> None:
    bar = _bar("sh600519", date(2026, 4, 20), 11.0)
    bar.preclose = 10.0

    result = _simulate_with_plugin(
        [bar],
        TargetPositionPlugin([("buy", 0.5)]),
        parameters={"limit_move_policy": {"buy": "defer", "sell": "reject"}},
    )

    assert result["events"][0]["no_trade_reason"] == "limit_up_buy_blocked"
    assert result["summary"]["execution_model"]["limit_move_policy"] == {"buy": "defer", "sell": "reject"}


def test_backtest_and_paper_trading_share_execution_fill_fields() -> None:
    backtest_bar = _bar("sh600519", date(2026, 4, 20), 10.0)
    backtest_result = _simulate_with_plugin([backtest_bar], TargetPositionPlugin([("buy", 0.5)]))
    execution = backtest_result["trades"][0]["execution"]

    assert sorted(execution.keys()) == [
        "fee",
        "filled_quantity",
        "matched",
        "mode",
        "price",
        "reject_reason",
        "rejection_code",
        "requested_quantity",
        "side",
        "symbol",
        "unfilled_quantity",
    ]


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
    assert payload["summary"]["research_report"]["format"] == "markdown"
    assert "回测研究报告" in payload["summary"]["research_report"]["content"]
    assert "sharpe_ratio" in payload["summary"]["report"]
    assert "drawdown_curve" in payload["summary"]["report"]
    assert payload["final_net_worth"] > 0


def test_backtest_research_report_api_returns_markdown(client, db) -> None:
    start = date(2026, 4, 20)
    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sh600519", start + timedelta(days=index), 10.0 + index * 0.2) for index in range(30)],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/backtest/research-report",
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
    assert payload["format"] == "markdown"
    assert "# sh600519 回测研究报告" in payload["content"]


def test_backtest_research_report_api_returns_empty_report_without_history(client) -> None:
    response = client.post(
        "/api/v1/backtest/research-report",
        json={
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "source": "unit-test-empty",
            "start_date": "2026-04-20",
            "end_date": "2026-04-21",
            "parameters": {"short_window": 3, "long_window": 5, "position_pct": 0.5},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "markdown"
    assert "暂无可用于生成研究报告的历史数据" in payload["content"]


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
    summary = provider_health_tracker.summary("baostock")
    assert summary.last_success_at is not None
    assert summary.recent_empty_count == 1
    assert summary.recent_failure_count == 0
    assert summary.runtime_health_level == "degraded"


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
    summary = provider_health_tracker.summary("manual")
    assert summary.recent_empty_count == 1
    assert summary.recent_failure_count == 0
    assert summary.runtime_health_level == "degraded"


def test_backtest_records_failure_for_local_daily_bar_read(db, monkeypatch) -> None:
    service = BacktestService()

    def fail_list_bars(self, **kwargs):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(MarketDailyBarStorage, "list_bars", fail_list_bars)

    with pytest.raises(RuntimeError, match="storage unavailable"):
        service.run_single_symbol_backtest(
            db,
            symbol="sh600519",
            strategy_type="moving_average",
            source="baostock",
        )

    summary = provider_health_tracker.summary("baostock")
    assert summary.recent_failure_count == 1
    assert summary.recent_empty_count == 0
    assert summary.last_failure_at is not None
    assert summary.runtime_health_level == "degraded"


def test_backtest_local_daily_bar_health_events_flow_into_source_health(db) -> None:
    MarketDailyBarStorage(db).upsert_bars(
        [_bar("sh600519", date(2026, 4, 20), 10.0)],
        source="baostock",
        adjustflag="2",
    )

    result = BacktestService().run_single_symbol_backtest(
        db,
        symbol="sh600519",
        strategy_type="moving_average",
        source="baostock",
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 20),
        parameters={"short_window": 1, "long_window": 1},
    )

    assert result["status"] == "completed"

    report = MarketSourceHealthService(db).build_daily_bar_source_health(symbols=["sh600519"], sources=["baostock"])
    item = report.sources[0]

    assert item.last_success_at is not None
    assert item.recent_failure_count == 0
    assert item.recent_empty_count == 0
    assert item.runtime_health_level == "healthy"


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


def test_backtest_runs_phase7_strategy(client, db) -> None:
    prices = [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 8.5, 9.2, 10, 10.4, 10.8, 11.0, 11.2, 11.4]
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
            "strategy_type": "signal_fusion",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "max_position_pct": 1.0,
            "parameters": {"position_pct": 0.2},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["strategy_type"] == "signal_fusion"
    assert payload["events"]
    assert "component_signals" in payload["events"][-1]
