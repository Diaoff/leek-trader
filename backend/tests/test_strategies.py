from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text

from app.market.providers.base import DailyBarSnapshot, IntradayBarSnapshot
from app.models.account import Account
from app.models.position import Position
from app.models.smart_selection_item import SmartSelectionItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus
from app.models.strategy import Strategy, StrategyExecutionMode, StrategyStatus, StrategyTargetType, StrategyType
from app.models.watchlist import WatchlistItem
from app.strategy.contracts import StrategySignal
from app.strategy.service import StrategyService
from app.strategy.strategies.macd import MacdStrategy
from app.strategy.strategies.moving_average import MovingAverageStrategy
from app.strategy.strategies.rl_trading import RLExitLevelAdvisor, RLTradingStrategy


def _legacy_signal(signal: StrategySignal) -> dict[str, object]:
    assert isinstance(signal, StrategySignal)
    return signal.to_legacy()


def _build_bars(
    symbol: str,
    closes: list[float],
    *,
    volumes: list[float] | None = None,
) -> list[DailyBarSnapshot]:
    start = date(2026, 4, 1)
    normalized_volumes = volumes or [1_000_000 + index * 10_000 for index in range(len(closes))]
    return [
        DailyBarSnapshot(
            symbol=symbol,
            trade_date=start + timedelta(days=index),
            open_price=close * 0.99,
            close_price=close,
            high_price=close * 1.01,
            low_price=close * 0.98,
            volume=normalized_volumes[index],
        )
        for index, close in enumerate(closes)
    ]


def _build_intraday_bars(closes: list[float], *, volumes: list[float] | None = None) -> list[IntradayBarSnapshot]:
    start = datetime(2026, 5, 7, 9, 35)
    normalized_volumes = volumes or [1000.0 for _ in closes]
    return [
        IntradayBarSnapshot(
            symbol="sh600519",
            bar_time=start + timedelta(minutes=5 * index),
            interval="5m",
            open_price=close - 0.1,
            high_price=close + 0.2,
            low_price=close - 0.2,
            close_price=close,
            volume=normalized_volumes[index],
            turnover=close * normalized_volumes[index],
        )
        for index, close in enumerate(closes)
    ]


def test_rl_trading_strategy_holds_when_history_is_insufficient() -> None:
    plugin = RLTradingStrategy()

    signal = _legacy_signal(plugin.evaluate("sh600000", _build_bars("sh600000", [10.0, 10.2, 10.4]), {"ma_long_window": 20}))

    assert signal["signal"] == "hold"
    assert signal["trigger_reason"] == "insufficient_history"
    assert signal["rl_action"]["action_type"] == "hold"


def test_strategy_create_rejects_invalid_moving_average_windows(client) -> None:
    response = client.post(
        "/api/v1/strategies",
        json={
            "name": "非法均线策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 10, "long_window": 5},
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"]["message"] == "invalid strategy parameters"
    assert "long_window must be greater than short_window" in payload["detail"]["errors"]


def test_rl_trading_baseline_buys_uptrend_and_caps_position() -> None:
    plugin = RLTradingStrategy()
    closes = [10 + index * 0.2 for index in range(30)]

    signal = _legacy_signal(plugin.evaluate("sh600000", _build_bars("sh600000", closes), {"max_position_pct": 0.3}))

    assert signal["signal"] == "buy"
    assert signal["trigger_reason"] == "rl_baseline_bullish_trend"
    assert signal["position_pct"] == 0.3
    assert signal["confidence"] > 0
    assert signal["rl_state"]["market_regime"] == "bullish"


def test_rl_trading_baseline_sells_downtrend() -> None:
    plugin = RLTradingStrategy()
    closes = [20 - index * 0.25 for index in range(30)]

    signal = _legacy_signal(plugin.evaluate("sh600000", _build_bars("sh600000", closes), {}))

    assert signal["signal"] == "sell"
    assert signal["rl_action"]["action_type"] == "sell"
    assert signal["trigger_reason"] == "rl_baseline_bearish_trend"


def test_rl_trading_min_confidence_suppresses_signal() -> None:
    plugin = RLTradingStrategy()
    closes = [10 + index * 0.2 for index in range(30)]

    signal = _legacy_signal(plugin.evaluate("sh600000", _build_bars("sh600000", closes), {"min_confidence": 0.99}))

    assert signal["signal"] == "hold"
    assert signal["position_pct"] == 0.0
    assert signal["trigger_reason"] == "min_confidence_not_met"


def test_rl_exit_advisor_widens_high_volatility_stop_and_protects_profit() -> None:
    low_vol_bars = _build_bars("sh600000", [10.0 + index * 0.02 for index in range(30)])
    high_vol_bars = _build_bars("sh600000", [10.0 + ((-1) ** index) * 0.8 + index * 0.03 for index in range(30)])
    advisor = RLExitLevelAdvisor(stop_loss_floor_pct=0.05, take_profit_rr=2.0)

    low = advisor.advise(entry_price=10.0, current_price=10.0, bars=low_vol_bars)
    high = advisor.advise(entry_price=10.0, current_price=10.0, bars=high_vol_bars)
    protected = advisor.advise(entry_price=10.0, current_price=11.5, bars=low_vol_bars, max_unrealized_return_pct=0.15)

    assert high["suggested_stop_loss_price"] < low["suggested_stop_loss_price"]
    assert protected["suggested_stop_loss_price"] > low["suggested_stop_loss_price"]
    assert low["suggested_take_profit_price"] > 10.0
    assert low["suggested_stop_loss_price"] < 10.0
    assert low["risk_reward_ratio"] >= 2.0


def _seed_recommendation(
    db,
    symbol: str,
    *,
    score: float = 82.0,
    timing: str = "STRONG BUY",
    position_pct: float = 12.0,
    snapshot_at: datetime | None = None,
    target_price: float = 118.0,
    stop_loss_price: float = 94.0,
) -> None:
    snapshot_at = snapshot_at or datetime.now(UTC)
    run = SmartSelectionRun(
        tenant_id="local",
        status=SmartSelectionRunStatus.SUCCEEDED,
        triggered_by="manual",
        started_at=snapshot_at,
        finished_at=snapshot_at,
        generated_at=snapshot_at,
        summary="test recommendation",
    )
    db.add(run)
    db.flush()

    db.add(
        SmartSelectionItem(
            run_id=run.id,
            symbol=symbol,
            code=symbol[2:],
            name="测试标的",
            score=score,
            price=100.0,
            change_pct=2.0,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            tags=["strong_buy"],
            reason="测试推荐",
            raw_detail={"timing": timing, "position_pct": position_pct},
        )
    )
    db.commit()


def _seed_recommendation_run(
    db,
    items: list[dict[str, object]],
    *,
    snapshot_at: datetime | None = None,
) -> None:
    snapshot_at = snapshot_at or datetime.now(UTC)
    run = SmartSelectionRun(
        tenant_id="local",
        status=SmartSelectionRunStatus.SUCCEEDED,
        triggered_by="manual",
        started_at=snapshot_at,
        finished_at=snapshot_at,
        generated_at=snapshot_at,
        summary="test recommendation batch",
    )
    db.add(run)
    db.flush()

    for item in items:
        symbol = str(item["symbol"])
        db.add(
            SmartSelectionItem(
                run_id=run.id,
                symbol=symbol,
                code=symbol[2:],
                name=str(item.get("name", "测试标的")),
                score=float(item.get("score", 82.0)),
                price=float(item.get("price", 100.0)),
                change_pct=float(item.get("change_pct", 2.0)),
                target_price=float(item.get("target_price", 118.0)),
                stop_loss_price=float(item.get("stop_loss_price", 94.0)),
                tags=list(item.get("tags", ["strong_buy"])),
                reason=str(item.get("reason", "测试推荐")),
                raw_detail={
                    "timing": item.get("timing", "STRONG BUY"),
                    "position_pct": item.get("position_pct", 12.0),
                },
            )
        )
    db.commit()


def _seed_position(db, symbol: str, *, quantity: int = 500, available_quantity: int | None = None, last_price: float = 100.0) -> Position:
    account = db.scalar(select(Account).where(Account.tenant_id == "local"))
    assert account is not None
    account.available_cash = Decimal("900000.00")
    account.total_equity = Decimal("1000000.00")
    position = Position(
        tenant_id="local",
        account_id=account.id,
        symbol=symbol,
        quantity=quantity,
        available_quantity=available_quantity if available_quantity is not None else quantity,
        frozen_quantity=0,
        average_cost=Decimal(str(last_price)),
        last_price=Decimal(str(last_price)),
        unrealized_pnl=Decimal("0.00"),
        realized_pnl=Decimal("0.00"),
        strategy_add_count=0,
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


def _patch_strategy_signal(
    monkeypatch,
    payload: dict,
    *,
    now: datetime | None = None,
    opening_window: bool = True,
    quote: dict[str, float | bool] | None = None,
) -> None:
    import app.api.strategies as strategies_api

    monkeypatch.setattr(
        strategies_api.service,
        "_evaluate_strategy",
        lambda strategy, symbol: {**payload, "symbol": symbol},
    )
    monkeypatch.setattr(strategies_api.service, "_is_opening_trade_window", lambda current=None: opening_window)
    if now is not None:
        monkeypatch.setattr(strategies_api.service, "_current_market_datetime", lambda: now)
    monkeypatch.setattr(
        strategies_api.service.trading_service,
        "_get_quote_snapshot",
        lambda symbol: quote or {"price": 100.0, "change_percent": 0.0, "is_halted": False},
    )


def _seed_special_attention_watchlist(db, symbol: str) -> None:
    db.add(
        WatchlistItem(
            tenant_id="local",
            symbol=symbol,
            group_id=None,
            sort_order=0,
            is_pinned=True,
            is_special_attention=True,
            note="重点关注",
        )
    )
    db.commit()


def test_list_strategies_returns_empty_by_default(client) -> None:
    response = client.get("/api/v1/strategies")

    assert response.status_code == 200
    assert response.json() == []


def test_list_strategies_handles_lowercase_execution_mode_values(db, client) -> None:
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "测试策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 5, "long_window": 20},
        },
    ).json()
    client.patch(f"/api/v1/strategies/{created['id']}", json={"status": "active"})
    db.execute(text("UPDATE strategies SET execution_mode = 'signal_only'"))
    db.commit()

    response = client.get("/api/v1/strategies")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert all(item["execution_mode"] == "signal_only" for item in payload)


def test_create_single_symbol_strategy_backfills_target_fields(client) -> None:
    response = client.post(
        "/api/v1/strategies",
        json={
            "name": "兼容单标的策略",
            "symbol": "SH600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 5, "long_window": 20},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "sh600036"
    assert payload["target_type"] == "single_symbol"
    assert payload["target_config"] == {"symbol": "sh600036"}
    assert payload["signal_symbol"] == "sh600036"
    assert payload["resolved_target_count"] == 1


def test_moving_average_plugin_emits_golden_cross_signal() -> None:
    plugin = MovingAverageStrategy()
    signal = _legacy_signal(plugin.evaluate(
        "sh600036",
        _build_bars(
            "sh600036",
            [10, 10.1, 10.15, 10.2, 10.25, 10.3, 10.35, 10.4, 10.45, 10.5, 10.55, 10.6, 10.65, 10.7, 10.75, 10.8, 10.85, 10.9, 10.95, 10.8, 10.7, 10.75, 10.9, 11.15],
        ),
        {"short_window": 3, "long_window": 5, "position_pct": 0.12, "volume_confirm_ratio": 1.05},
    ))

    assert signal["signal"] == "buy"
    assert signal["strength"] == "strong"
    assert signal["trigger_reason"] == "golden_cross"
    assert signal["filter_passed"] is True
    assert signal["filter_reasons"] == []


def test_moving_average_plugin_avoids_repeated_buy_on_existing_uptrend() -> None:
    plugin = MovingAverageStrategy()
    signal = _legacy_signal(plugin.evaluate(
        "sh600036",
        _build_bars("sh600036", [10, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 11.0, 11.05, 11.1, 11.15, 11.2, 11.25, 11.3, 11.33, 11.36, 11.4, 11.43, 11.46, 11.48, 11.5]),
        {"short_window": 3, "long_window": 5, "position_pct": 0.12},
    ))

    assert signal["signal"] == "hold"
    assert signal["trigger_reason"] == "waiting_for_confirmation"


def test_moving_average_plugin_returns_hold_when_history_is_insufficient() -> None:
    plugin = MovingAverageStrategy()
    signal = _legacy_signal(plugin.evaluate(
        "sh600036",
        _build_bars("sh600036", [10, 10.1, 10.2, 10.3, 10.4, 10.45]),
        {"short_window": 3, "long_window": 5},
    ))

    assert signal["signal"] == "hold"
    assert signal["trigger_reason"] == "insufficient_history"


def test_moving_average_plugin_blocks_golden_cross_when_volume_is_weak() -> None:
    plugin = MovingAverageStrategy()
    signal = _legacy_signal(plugin.evaluate(
        "sh600036",
        _build_bars(
            "sh600036",
            [10, 10.1, 10.15, 10.2, 10.25, 10.3, 10.35, 10.4, 10.45, 10.5, 10.55, 10.6, 10.65, 10.7, 10.75, 10.8, 10.85, 10.9, 10.95, 10.8, 10.7, 10.75, 10.9, 11.15],
            volumes=[1_000_000 + index * 10_000 for index in range(23)] + [850_000],
        ),
        {"short_window": 3, "long_window": 5, "position_pct": 0.12, "volume_confirm_ratio": 1.05},
    ))

    assert signal["signal"] == "hold"
    assert signal["trigger_reason"] == "golden_cross"
    assert signal["filter_passed"] is False
    assert "volume_not_confirmed" in signal["filter_reasons"]


def test_moving_average_plugin_blocks_trend_follow_buy_when_price_is_overheated() -> None:
    plugin = MovingAverageStrategy()
    signal = _legacy_signal(plugin.evaluate(
        "sh600036",
        _build_bars("sh600036", [10.07, 10.1, 10.15, 10.22, 10.25, 10.3, 10.37, 10.45, 10.52, 10.58, 10.61, 10.69, 10.73, 10.77, 10.84, 10.87, 10.95, 11.02, 11.08, 11.22, 11.31, 11.39, 11.58, 11.82]),
        {"short_window": 3, "long_window": 5, "position_pct": 0.12},
    ))

    assert signal["signal"] == "hold"
    assert signal["trigger_reason"] == "trend_follow_buy"
    assert signal["filter_passed"] is False
    assert "price_too_stretched" in signal["filter_reasons"]


def test_macd_plugin_emits_golden_cross_and_death_cross_signals() -> None:
    plugin = MacdStrategy()

    buy_signal = _legacy_signal(plugin.evaluate(
        "sh600036",
        _build_bars(
            "sh600036",
            [10.12, 10.17, 10.25, 10.31, 10.42, 10.48, 10.58, 10.64, 10.7, 10.82, 10.92, 11.01, 11.12, 11.24, 11.35, 11.27, 11.22, 11.2, 11.19, 11.26, 11.31, 11.35, 11.39, 11.49],
            volumes=[1_000_000 + index * 6_000 for index in range(23)] + [1_350_000],
        ),
        {"fast_period": 4, "slow_period": 8, "signal_period": 3, "position_pct": 0.1, "max_volatility_20": 0.12},
    ))
    sell_signal = _legacy_signal(plugin.evaluate(
        "sh600036",
        _build_bars(
            "sh600036",
            [10, 10, 10, 10, 10, 10, 10, 10.3, 10.6, 10.9, 11.2, 11.5, 11.8, 12.1, 12.4, 12.7, 13.0, 13.2, 10.36, 9.9, 12.15, 9.84, 12.75, 9.62],
        ),
        {"fast_period": 4, "slow_period": 8, "signal_period": 3, "position_pct": 0.1},
    ))

    assert buy_signal["signal"] == "buy"
    assert buy_signal["trigger_reason"] == "macd_golden_cross_above_zero"
    assert buy_signal["strength"] == "strong"
    assert buy_signal["filter_passed"] is True
    assert sell_signal["signal"] == "sell"
    assert sell_signal["trigger_reason"] == "macd_death_cross_below_zero"


def test_macd_plugin_distinguishes_zero_axis_strength() -> None:
    plugin = MacdStrategy()

    strong_signal = _legacy_signal(plugin.evaluate(
        "sh600036",
        _build_bars(
            "sh600036",
            [10.12, 10.17, 10.25, 10.31, 10.42, 10.48, 10.58, 10.64, 10.7, 10.82, 10.92, 11.01, 11.12, 11.24, 11.35, 11.27, 11.22, 11.2, 11.19, 11.26, 11.31, 11.35, 11.39, 11.49],
            volumes=[1_000_000 + index * 6_000 for index in range(23)] + [1_350_000],
        ),
        {"fast_period": 4, "slow_period": 8, "signal_period": 3, "position_pct": 0.1, "max_volatility_20": 0.12},
    ))
    weak_signal = _legacy_signal(plugin.evaluate(
        "sh600036",
        _build_bars(
            "sh600036",
            [15, 14.9, 14.8, 14.7, 14.6, 14.5, 14.4, 14.3, 14.2, 14.1, 14.0, 13.9, 13.8, 13.7, 13.6, 13.5, 13.4, 13.3, 13.18, 13.06, 12.94, 12.82, 12.7, 12.62],
            volumes=[1_000_000 for _ in range(23)] + [900_000],
        ),
        {"fast_period": 3, "slow_period": 6, "signal_period": 3, "position_pct": 0.1},
    ))

    assert strong_signal["signal"] == "buy"
    assert strong_signal["strength"] == "strong"
    assert strong_signal["trigger_reason"] == "macd_golden_cross_above_zero"
    assert strong_signal["filter_passed"] is True
    assert weak_signal["signal"] == "hold"
    assert weak_signal["trigger_reason"] == "macd_golden_cross_below_zero"
    assert weak_signal["filter_passed"] is False
    assert "countertrend_macd_needs_confirmation" in weak_signal["filter_reasons"]
    assert "volume_not_confirmed" in weak_signal["filter_reasons"]


def test_builtin_phase7_strategies_return_native_strategy_signal() -> None:
    from app.strategy.strategies.bollinger_band import BollingerBandStrategy
    from app.strategy.strategies.kdj_momentum import KdjMomentumStrategy
    from app.strategy.strategies.signal_fusion import SignalFusionStrategy

    cases = [
        (
            MovingAverageStrategy(),
            [10, 10.1, 10.15, 10.2, 10.25, 10.3, 10.35, 10.4, 10.45, 10.5, 10.55, 10.6, 10.65, 10.7, 10.75, 10.8, 10.85, 10.9, 10.95, 10.8, 10.7, 10.75, 10.9, 11.15],
            {"short_window": 3, "long_window": 5, "position_pct": 0.12, "volume_confirm_ratio": 1.05},
        ),
        (
            MacdStrategy(),
            [10.12, 10.17, 10.25, 10.31, 10.42, 10.48, 10.58, 10.64, 10.7, 10.82, 10.92, 11.01, 11.12, 11.24, 11.35, 11.27, 11.22, 11.2, 11.19, 11.26, 11.31, 11.35, 11.39, 11.49],
            {"fast_period": 4, "slow_period": 8, "signal_period": 3, "position_pct": 0.1, "max_volatility_20": 0.12},
        ),
        (KdjMomentumStrategy(), [10, 10.2, 10.1, 10.3, 10.2, 10.4, 10.3, 10.5, 10.7, 10.9, 11.0, 10.8], {"kdj_period": 5}),
        (BollingerBandStrategy(), [10, 10.2, 10.1, 10.3, 10.2, 10.4, 10.3, 10.5, 9.5, 10.1], {"boll_period": 5, "stddev_multiplier": 2}),
        (RLTradingStrategy(), [10 + index * 0.2 for index in range(30)], {"max_position_pct": 0.3}),
        (SignalFusionStrategy(), [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 8.5, 9.2, 10, 10.4, 10.8, 11.0, 11.2, 11.4], {}),
    ]

    for plugin, closes, parameters in cases:
        signal = plugin.evaluate("sh600000", _build_bars("sh600000", closes), parameters)
        assert isinstance(signal, StrategySignal)
        legacy = signal.to_legacy()
        for key in (
            "signal",
            "strength",
            "trigger_reason",
            "position_pct",
            "stop_loss_price",
            "take_profit_price",
            "requires_recommendation_confirmation",
        ):
            assert key in legacy


def test_native_strategy_signal_preserves_manager_gate_suppression() -> None:
    signal = MovingAverageStrategy().evaluate(
        "sh600036",
        _build_bars(
            "sh600036",
            [10, 10.1, 10.15, 10.2, 10.25, 10.3, 10.35, 10.4, 10.45, 10.5, 10.55, 10.6, 10.65, 10.7, 10.75, 10.8, 10.85, 10.9, 10.95, 10.8, 10.7, 10.75, 10.9, 11.15],
            volumes=[1_000_000 + index * 10_000 for index in range(23)] + [850_000],
        ),
        {"short_window": 3, "long_window": 5, "position_pct": 0.12, "volume_confirm_ratio": 1.05},
    )

    assert isinstance(signal, StrategySignal)
    assert signal.action == "hold"
    legacy = signal.to_legacy()
    assert legacy["trigger_reason"] == "golden_cross"
    assert legacy["filter_passed"] is False


def test_rl_native_strategy_signal_preserves_rl_metadata_in_legacy_payload() -> None:
    signal = RLTradingStrategy().evaluate("sh600000", _build_bars("sh600000", [10 + index * 0.2 for index in range(30)]), {"max_position_pct": 0.3})

    assert isinstance(signal, StrategySignal)
    legacy = signal.to_legacy()
    assert legacy["rl_action"]["action_type"] == "buy"
    assert legacy["rl_action"]["target_position_pct"] == 0.3
    assert legacy["rl_state"]["market_regime"] == "bullish"


def test_strategy_evaluation_uses_history_fallback_without_history_unavailable() -> None:
    class EmptyHistoryProvider:
        name = "eastmoney"

        def fetch_daily_bars(self, symbol: str, limit: int = 60):
            return []

    class FallbackHistoryProvider:
        name = "sina"

        def fetch_daily_bars(self, symbol: str, limit: int = 60):
            return _build_bars(symbol, [10, 10, 10, 10, 10, 9, 8, 9, 10, 12])

    service = StrategyService()
    service.history_service.providers = [EmptyHistoryProvider(), FallbackHistoryProvider()]
    strategy = Strategy(
        tenant_id="local",
        name="fallback strategy",
        symbol="301667.SZ",
        target_type=StrategyTargetType.SINGLE_SYMBOL,
        target_config={"symbol": "301667.SZ"},
        strategy_type=StrategyType.MOVING_AVERAGE,
        status=StrategyStatus.ACTIVE,
        execution_mode=StrategyExecutionMode.SIGNAL_ONLY,
        parameters={"short_window": 3, "long_window": 5, "position_pct": 0.1},
    )

    signal = service._evaluate_strategy(strategy, "301667.SZ")

    assert signal["symbol"] == "301667.SZ"
    assert signal["trigger_reason"] != "history_unavailable"


def test_intraday_timing_confirms_buy_signal() -> None:
    service = StrategyService()
    service._current_market_datetime = lambda: datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    strategy = Strategy(
        tenant_id="local",
        name="intraday buy",
        symbol="sh600519",
        target_type=StrategyTargetType.SINGLE_SYMBOL,
        target_config={"symbol": "sh600519"},
        strategy_type=StrategyType.MOVING_AVERAGE,
        status=StrategyStatus.ACTIVE,
        execution_mode=StrategyExecutionMode.AUTO_TRADE,
        parameters={"intraday_volume_ratio_min": 1.2},
    )
    service.market_data_service.get_intraday_bars = lambda symbol, interval="5m", limit=120: _build_intraday_bars(
        [100.0, 100.4, 100.8, 101.2],
        volumes=[1000, 1000, 1000, 2000],
    )
    signal = {"signal": "buy", "execution_blockers": [], "stop_loss_price": 95.0, "take_profit_price": 110.0}
    service._apply_intraday_timing_gate(strategy, signal, symbol="sh600519", raw_signal="buy")

    assert signal["signal"] == "buy"
    assert signal["intraday_timing_status"] == "confirmed"
    assert signal["intraday_trigger_reason"] == "intraday_buy_confirmed"


def test_intraday_timing_blocks_buy_below_vwap() -> None:
    service = StrategyService()
    service._current_market_datetime = lambda: datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    service.market_data_service.get_intraday_bars = lambda symbol, interval="5m", limit=120: _build_intraday_bars(
        [100.0, 102.0, 103.0, 99.0],
        volumes=[1000, 1000, 1000, 2000],
    )
    strategy = Strategy(
        tenant_id="local",
        name="intraday block",
        symbol="sh600519",
        target_type=StrategyTargetType.SINGLE_SYMBOL,
        target_config={"symbol": "sh600519"},
        strategy_type=StrategyType.MOVING_AVERAGE,
        status=StrategyStatus.ACTIVE,
        execution_mode=StrategyExecutionMode.AUTO_TRADE,
        parameters={},
    )
    signal = {"signal": "buy", "execution_blockers": []}

    service._apply_intraday_timing_gate(strategy, signal, symbol="sh600519", raw_signal="buy")

    assert signal["signal"] == "hold"
    assert signal["intraday_timing_status"] == "blocked"
    assert "intraday_below_vwap" in signal["execution_blockers"]


def test_intraday_timing_allows_exit_on_stop_loss() -> None:
    service = StrategyService()
    service._current_market_datetime = lambda: datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    service.market_data_service.get_intraday_bars = lambda symbol, interval="5m", limit=120: _build_intraday_bars([100.0, 99.0, 98.0])
    strategy = Strategy(
        tenant_id="local",
        name="intraday exit",
        symbol="sh600519",
        target_type=StrategyTargetType.SINGLE_SYMBOL,
        target_config={"symbol": "sh600519"},
        strategy_type=StrategyType.MOVING_AVERAGE,
        status=StrategyStatus.ACTIVE,
        execution_mode=StrategyExecutionMode.AUTO_TRADE,
        parameters={},
    )
    signal = {"signal": "sell", "execution_blockers": [], "stop_loss_price": 98.5}

    service._apply_intraday_timing_gate(strategy, signal, symbol="sh600519", raw_signal="sell")

    assert signal["signal"] == "sell"
    assert signal["intraday_timing_status"] == "confirmed"
    assert signal["intraday_trigger_reason"] == "intraday_stop_loss_triggered"


def test_intraday_timing_unavailable_keeps_daily_signal() -> None:
    service = StrategyService()
    service._current_market_datetime = lambda: datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    service.market_data_service.get_intraday_bars = lambda symbol, interval="5m", limit=120: []
    strategy = Strategy(
        tenant_id="local",
        name="intraday unavailable",
        symbol="sh600519",
        target_type=StrategyTargetType.SINGLE_SYMBOL,
        target_config={"symbol": "sh600519"},
        strategy_type=StrategyType.MOVING_AVERAGE,
        status=StrategyStatus.ACTIVE,
        execution_mode=StrategyExecutionMode.AUTO_TRADE,
        parameters={},
    )
    signal = {"signal": "buy", "execution_blockers": []}

    service._apply_intraday_timing_gate(strategy, signal, symbol="sh600519", raw_signal="buy")

    assert signal["signal"] == "buy"
    assert signal["intraday_timing_status"] == "unavailable"


def test_strategy_readiness_transitions_with_paper_runs(client, monkeypatch) -> None:
    import app.api.strategies as strategies_api

    monkeypatch.setattr(
        strategies_api.service,
        "_load_price_bars",
        lambda symbol, limit: _build_bars(symbol, [10, 10, 10, 10, 10, 9, 8, 9, 10, 12]),
    )

    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "纸面验证策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 3, "long_window": 5, "position_pct": 0.2},
        },
    ).json()

    initial = next(item for item in client.get("/api/v1/strategies").json() if item["id"] == created["id"])
    assert initial["readiness_status"] == "observing"

    client.post(f"/api/v1/strategies/{created['id']}/run")
    client.post(f"/api/v1/strategies/{created['id']}/run")
    client.post(f"/api/v1/strategies/{created['id']}/run")

    refreshed = next(item for item in client.get("/api/v1/strategies").json() if item["id"] == created["id"])
    assert refreshed["readiness_status"] == "paper_verified"
    assert refreshed["readiness_summary"] == "已通过纸面验证"


def test_create_update_and_run_strategy_persists_state(client, monkeypatch) -> None:
    import app.api.strategies as strategies_api

    monkeypatch.setattr(
        strategies_api.service,
        "_load_price_bars",
        lambda symbol, limit: _build_bars(symbol, [10, 10, 10, 10, 10, 9, 8, 9, 10, 12]),
    )

    create_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "测试均线策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 5, "position_pct": 0.2},
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()

    update_response = client.patch(
        f"/api/v1/strategies/{created['id']}",
        json={
            "status": "active",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 3, "long_window": 5, "position_pct": 0.15},
        },
    )
    assert update_response.status_code == 200

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["strategy_id"] == created["id"]
    assert run_payload["status"] == "success"
    assert run_payload["created_at"].endswith(("Z", "+00:00"))
    assert run_payload["signal"]["signal"] in {"buy", "sell", "reduce", "hold"}
    assert run_payload["execution_mode"] == "auto_trade"
    assert "execution_blockers" in run_payload

    list_response = client.get("/api/v1/strategies")
    refreshed = next(item for item in list_response.json() if item["id"] == created["id"])
    assert refreshed["latest_run_status"] == "success"
    assert refreshed["latest_run_at"].endswith(("Z", "+00:00"))
    assert refreshed["run_count_today"] == 1
    assert refreshed["total_run_count"] == 1
    assert refreshed["latest_signal"] in {"buy", "sell", "reduce", "hold"}
    assert refreshed["latest_signal_summary"] is not None


def test_strategy_run_timestamps_preserve_utc_instant(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": "time_check",
            "entry_price_ref": 10.0,
        },
    )

    create_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "timezone strategy",
            "symbol": "sh600519",
            "target_type": "single_symbol",
            "target_config": {"symbol": "sh600519"},
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 5},
        },
    )
    strategy_id = create_response.json()["id"]

    run_payload = client.post(f"/api/v1/strategies/{strategy_id}/run").json()
    created_at = datetime.fromisoformat(run_payload["created_at"].replace("Z", "+00:00"))

    assert created_at.tzinfo is not None
    assert abs((datetime.now(UTC) - created_at).total_seconds()) < 60


def test_get_latest_strategy_run_returns_persisted_result(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600036",
            "strategy": "moving_average",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": "waiting_for_confirmation",
            "entry_price_ref": 100.0,
            "position_pct": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "最新运行查询策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 5},
        },
    ).json()

    run_payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()
    latest_response = client.get("/api/v1/strategies/runs/latest")

    assert latest_response.status_code == 200
    latest_payload = latest_response.json()
    assert latest_payload["id"] == run_payload["id"]
    assert latest_payload["strategy_id"] == created["id"]
    assert latest_payload["status"] == "success"


def test_get_strategy_run_history_returns_latest_runs_in_desc_order(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600036",
            "strategy": "moving_average",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": "waiting_for_confirmation",
            "entry_price_ref": 100.0,
            "position_pct": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
        },
    )
    first = client.post(
        "/api/v1/strategies",
        json={
            "name": "历史策略一",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 5},
        },
    ).json()
    second = client.post(
        "/api/v1/strategies",
        json={
            "name": "历史策略二",
            "symbol": "sz000001",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 5},
        },
    ).json()

    first_run = client.post(f"/api/v1/strategies/{first['id']}/run").json()
    second_run = client.post(f"/api/v1/strategies/{second['id']}/run").json()

    history_response = client.get("/api/v1/strategies/runs/history", params={"limit": 1})
    filtered_response = client.get("/api/v1/strategies/runs/history", params={"strategy_id": first["id"]})

    assert history_response.status_code == 200
    history_payload = history_response.json()["runs"]
    assert len(history_payload) == 1
    assert history_payload[0]["id"] == second_run["id"]

    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()["runs"]
    assert len(filtered_payload) == 1
    assert filtered_payload[0]["id"] == first_run["id"]
    assert filtered_payload[0]["strategy_id"] == first["id"]


def test_delete_strategy_hides_definition_and_preserves_run_history(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600036",
            "strategy": "moving_average",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": "waiting_for_confirmation",
            "entry_price_ref": 100.0,
            "position_pct": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "待删除策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 5},
        },
    ).json()
    run_payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()

    delete_response = client.delete(f"/api/v1/strategies/{created['id']}")
    list_response = client.get("/api/v1/strategies")
    history_response = client.get("/api/v1/strategies/runs/history", params={"strategy_id": created["id"]})
    run_deleted_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted", "id": created["id"]}
    assert all(item["id"] != created["id"] for item in list_response.json())
    assert history_response.status_code == 200
    history_payload = history_response.json()["runs"]
    assert len(history_payload) == 1
    assert history_payload[0]["id"] == run_payload["id"]
    assert history_payload[0]["strategy_id"] == created["id"]
    assert run_deleted_response.status_code == 404


def test_delete_missing_strategy_returns_not_found(client) -> None:
    response = client.delete("/api/v1/strategies/999999")

    assert response.status_code == 404


def test_signal_only_strategy_returns_structured_plan_without_creating_order(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600036",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 112.0,
            "position_pct": 0.1,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
            "filter_passed": True,
            "filter_reasons": [],
            "trend_ok": True,
            "volume_ok": True,
            "volatility_ok": True,
            "stretch_ok": True,
            "market_regime_bias": "supportive",
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "纯信号策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 7, "position_pct": 0.1},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution_mode"] == "signal_only"
    assert payload["order_submitted"] is False
    assert payload["reason"] == "signal_only_mode"
    assert payload["strength"] == "strong"
    assert payload["trigger_reason"] == "golden_cross"
    assert payload["execution_blockers"] == ["signal_only_mode"]
    assert payload["position_pct"] == 0.1
    assert payload["signal"]["filter_passed"] is True
    assert client.get("/api/v1/orders").json() == []


def test_auto_trade_filtered_buy_signal_is_downgraded_to_hold_without_order(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600036",
            "strategy": "moving_average",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 112.0,
            "position_pct": 0.0,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": False,
            "filter_passed": False,
            "filter_reasons": ["volume_not_confirmed"],
            "trend_ok": True,
            "volume_ok": False,
            "volatility_ok": True,
            "stretch_ok": True,
            "market_regime_bias": "neutral",
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "过滤后观望策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 3, "long_window": 7, "position_pct": 0.1},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["signal"]["signal"] == "hold"
    assert payload["reason"] == "signal_hold"
    assert payload["order_submitted"] is False
    assert payload["trigger_reason"] == "golden_cross"
    assert payload["signal"]["filter_passed"] is False
    assert payload["signal"]["filter_reasons"] == ["volume_not_confirmed"]
    assert client.get("/api/v1/orders").json() == []


def test_auto_trade_strategy_requires_recommendation_confirmation(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 118.0,
            "position_pct": 0.2,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "自动交易策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.2, "intraday_timing_enabled": False},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution_mode"] == "auto_trade"
    assert payload["order_submitted"] is False
    assert payload["reason"] == "recommendation_missing"
    assert payload["execution_blockers"] == ["recommendation_missing"]
    assert client.get("/api/v1/orders").json() == []


def test_auto_trade_strategy_can_bypass_recommendation_confirmation_for_simulation(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 120.0,
            "position_pct": 0.1,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "宽松确认模拟策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {
                "short_window": 5,
                "long_window": 20,
                "position_pct": 0.1,
                "bypass_recommendation_confirmation": True,
                "intraday_timing_enabled": False,
            },
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["order_submitted"] is True
    assert payload["recommendation_confirmed"] is True
    assert payload["confirmation_source"] == "simulation_bypass"
    assert payload["execution_blockers"] == []


def test_special_attention_watchlist_symbol_can_pass_buy_gate_without_recommendation(db, client, monkeypatch) -> None:
    _seed_special_attention_watchlist(db, "sh600519")
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 118.0,
            "position_pct": 0.1,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "重点关注自动交易策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1, "intraday_timing_enabled": False},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["order_submitted"] is True
    assert payload["recommendation_confirmed"] is True
    assert payload["confirmation_source"] == "special_attention_watchlist"
    assert payload["recommendation_snapshot_date"] is None
    assert payload["position_add_path"] == "new_position"
    assert payload["signal"]["confirmation_source"] == "special_attention_watchlist"
    assert payload["signal"]["recommendation_timing"] is None
    assert payload["execution_blockers"] == []


def test_auto_trade_strategy_places_order_after_recommendation_gate_passes(db, client, monkeypatch) -> None:
    _seed_recommendation(db, "sh600519", score=88.0, timing="STRONG BUY", position_pct=8.0)
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 120.0,
            "position_pct": 0.15,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "自动交易策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.15, "intraday_timing_enabled": False},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution_mode"] == "auto_trade"
    assert payload["order_submitted"] is True
    assert payload["order_status"] == "filled"
    assert payload["recommendation_confirmed"] is True
    assert payload["position_pct"] == 0.08
    assert payload["reason"] == "order_submitted"
    assert payload["quantity"] == 800
    assert len(payload["items"]) == 1
    assert payload["items"][0]["symbol"] == "sh600519"

    position = db.scalar(select(Position).where(Position.symbol == "sh600519"))
    assert position is not None
    assert position.quantity == 800
    assert str(position.stop_loss_price) == "95.0000"
    assert str(position.take_profit_price) == "118.0000"
    assert position.strategy_add_count == 0
    assert position.exit_guard_status == "active"
    assert position.exit_trigger_reason is None


def test_auto_trade_sell_signal_is_blocked_when_available_quantity_insufficient(client, monkeypatch) -> None:
    buy_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )
    assert buy_response.status_code == 200

    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "sell",
            "strength": "strong",
            "trigger_reason": "death_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 98.0,
            "take_profit_price": 110.0,
            "position_pct": 1.0,
            "market_regime": "bearish",
            "requires_recommendation_confirmation": False,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "卖出策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.15, "intraday_timing_enabled": False},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["order_submitted"] is False
    assert payload["reason"] == "insufficient_position"
    assert payload["execution_blockers"] == ["insufficient_position"]


def test_reduce_signal_creates_partial_sell_order(client, monkeypatch) -> None:
    buy_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 1000,
            "price": 100,
        },
    )
    assert buy_response.status_code == 200

    from app.core.db import SessionLocal
    from app.models.position import Position
    from sqlalchemy import select

    with SessionLocal() as session:
        position = session.scalar(select(Position).where(Position.symbol == "sh600519"))
        assert position is not None
        position.last_buy_date = date(2026, 4, 21)
        session.commit()

    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "macd",
            "signal": "reduce",
            "strength": "weak",
            "trigger_reason": "macd_histogram_contracting",
            "entry_price_ref": 100.0,
            "stop_loss_price": 97.0,
            "take_profit_price": 110.0,
            "position_pct": 0.4,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "减仓策略",
            "symbol": "sh600519",
            "strategy_type": "macd",
            "execution_mode": "auto_trade",
            "parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9, "position_pct": 0.15},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["order_submitted"] is True
    assert payload["side"] == "sell"
    assert payload["quantity"] == 400
    assert payload["signal"]["signal"] == "reduce"


def test_auto_trade_buy_signal_uses_quote_price_for_execution(db, client, monkeypatch) -> None:
    import app.api.strategies as strategies_api

    _seed_recommendation(db, "sh600519", score=88.0, timing="STRONG BUY", position_pct=20.0)
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 120.0,
            "position_pct": 0.15,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
    )
    monkeypatch.setattr(
        strategies_api.service.trading_service,
        "_get_quote_snapshot",
        lambda symbol: {"price": 1449.65, "change_percent": 0.0, "is_halted": False},
    )

    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "行情价格执行策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.2, "intraday_timing_enabled": False},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["order_submitted"] is True
    assert payload["price"] == 1449.65


def test_auto_trade_hold_signal_skips_order(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600036",
            "strategy": "moving_average",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": "waiting_for_confirmation",
            "entry_price_ref": 100.0,
            "position_pct": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "观望自动策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 3, "long_window": 99, "position_pct": 0.1},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["signal"]["signal"] == "hold"
    assert payload["order_submitted"] is False
    assert payload["reason"] == "signal_hold"
    assert client.get("/api/v1/orders").json() == []


def test_special_attention_target_strategy_runs_all_resolved_symbols(db, client, monkeypatch) -> None:
    import app.api.strategies as strategies_api

    _seed_special_attention_watchlist(db, "sh600519")
    _seed_special_attention_watchlist(db, "sz000001")

    def fake_evaluate(strategy, symbol: str) -> dict[str, object]:
        if symbol == "sh600519":
            return {
                "symbol": symbol,
                "strategy": "moving_average",
                "signal": "buy",
                "strength": "strong",
                "trigger_reason": "golden_cross",
                "entry_price_ref": 100.0,
                "stop_loss_price": 95.0,
                "take_profit_price": 118.0,
                "position_pct": 0.1,
                "market_regime": "bullish",
                "requires_recommendation_confirmation": True,
            }
        return {
            "symbol": symbol,
            "strategy": "moving_average",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": "waiting_for_confirmation",
            "entry_price_ref": 100.0,
            "position_pct": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
        }

    monkeypatch.setattr(strategies_api.service, "_evaluate_strategy", fake_evaluate)
    monkeypatch.setattr(strategies_api.service, "_is_opening_trade_window", lambda now=None: True)
    monkeypatch.setattr(
        strategies_api.service.trading_service,
        "_get_quote_snapshot",
        lambda symbol: {"price": 100.0, "change_percent": 0.0, "is_halted": False},
    )

    create_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "重点关注池策略",
            "target_type": "special_attention",
            "target_config": {},
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1, "intraday_timing_enabled": False},
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["symbol"] == ""
    assert created["target_type"] == "special_attention"
    assert created["signal_symbol"] == "sh600519 等 2 只"
    assert created["resolved_target_count"] == 2

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["order_submitted"] is True
    assert payload["signal"]["symbol"] == "sh600519"
    assert payload["items"][0]["symbol"] == "sh600519"
    assert payload["items"][0]["order_submitted"] is True
    assert payload["items"][0]["confirmation_source"] == "special_attention_watchlist"
    assert payload["items"][1]["symbol"] == "sz000001"
    assert payload["items"][1]["reason"] == "signal_hold"
    assert len(payload["items"]) == 2


def test_special_attention_target_strategy_includes_existing_positions_as_fallback(db, client, monkeypatch) -> None:
    _seed_position(db, "sh600519")
    _patch_strategy_signal(
        monkeypatch,
        {
            "strategy": "moving_average",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": "fallback_position_scan",
            "entry_price_ref": 100.0,
            "position_pct": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
        },
    )

    create_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "持仓兜底扫描策略",
            "target_type": "special_attention",
            "target_config": {},
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1, "intraday_timing_enabled": False},
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["signal_symbol"] == "sh600519"
    assert created["resolved_target_count"] == 1

    payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()

    assert [item["symbol"] for item in payload["items"]] == ["sh600519"]
    assert len(payload["items"]) == 1


def test_existing_position_fallback_allows_auto_trade_add(db, client, monkeypatch) -> None:
    position = _seed_position(db, "sh600519", quantity=500, last_price=100.0)
    _patch_strategy_signal(
        monkeypatch,
        {
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "fallback_position_add",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 118.0,
            "position_pct": 0.1,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "持仓兜底允许补仓",
            "target_type": "special_attention",
            "target_config": {},
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1, "intraday_timing_enabled": False},
        },
    ).json()

    payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()

    assert payload["order_submitted"] is True
    assert payload["recommendation_confirmed"] is True
    assert payload["confirmation_source"] == "existing_position"
    assert payload["position_add_path"] == "first_add"
    assert payload["quantity"] == 500
    db.refresh(position)
    assert position.quantity == 1000
    assert position.strategy_add_count == 1


def test_special_attention_target_strategy_includes_latest_smart_selection_scope(db, client, monkeypatch) -> None:
    _seed_special_attention_watchlist(db, "sh600519")
    _seed_special_attention_watchlist(db, "sz000001")
    _seed_recommendation_run(
        db,
        [
            {"symbol": "sh601318", "score": 96.0},
            {"symbol": "sh600519", "score": 91.0},
            {"symbol": "sz300750", "score": 93.0},
        ],
    )
    _patch_strategy_signal(
        monkeypatch,
        {
            "strategy": "moving_average",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": "waiting_for_confirmation",
            "entry_price_ref": 100.0,
            "position_pct": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
        },
    )

    create_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "动态组合范围策略",
            "target_type": "special_attention",
            "target_config": {},
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1, "intraday_timing_enabled": False},
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["signal_symbol"] == "sh600519 等 4 只"
    assert created["resolved_target_count"] == 4

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert [item["symbol"] for item in payload["items"]] == [
        "sh600519",
        "sz000001",
        "sh601318",
        "sz300750",
    ]
    assert len(payload["items"]) == 4


def test_special_attention_watchlist_bypasses_recommendation_controls_without_inheriting_them(db, client, monkeypatch) -> None:
    _seed_special_attention_watchlist(db, "sh600519")
    _seed_recommendation(
        db,
        "sh600519",
        score=25.0,
        timing="SELL",
        position_pct=3.0,
        target_price=150.0,
        stop_loss_price=80.0,
        snapshot_at=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
    )
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 118.0,
            "position_pct": 0.1,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
        now=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "重点关注绕过推荐池参数",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1, "intraday_timing_enabled": False},
        },
    ).json()

    payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()

    assert payload["order_submitted"] is True
    assert payload["confirmation_source"] == "special_attention_watchlist"
    assert payload["position_pct"] == 0.1
    assert payload["stop_loss_price"] == 95.0
    assert payload["take_profit_price"] == 118.0
    assert payload["signal"]["recommendation_score"] is None
    assert payload["signal"]["recommendation_timing"] is None


def test_auto_trade_strategy_prefers_current_trading_day_recommendation_snapshot(db, client, monkeypatch) -> None:
    _seed_recommendation(db, "sh600519", position_pct=12.0, snapshot_at=datetime(2026, 4, 21, 9, 0, tzinfo=UTC))
    _seed_recommendation(db, "sh600519", position_pct=5.0, snapshot_at=datetime(2026, 4, 22, 9, 30, tzinfo=UTC))
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 120.0,
            "position_pct": 0.15,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
        now=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "当日推荐优先策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.15, "intraday_timing_enabled": False},
        },
    ).json()

    payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()

    assert payload["order_submitted"] is True
    assert payload["confirmation_source"] == "smart_selection"
    assert payload["recommendation_snapshot_date"] == "2026-04-22"
    assert payload["position_pct"] == 0.05
    assert payload["quantity"] == 500


def test_auto_trade_strategy_falls_back_to_previous_trading_day_recommendation_snapshot(db, client, monkeypatch) -> None:
    _seed_recommendation(db, "sh600519", position_pct=12.0, snapshot_at=datetime(2026, 4, 21, 9, 0, tzinfo=UTC))
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 120.0,
            "position_pct": 0.15,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
        now=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "上一交易日推荐回退",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.15, "intraday_timing_enabled": False},
        },
    ).json()

    payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()

    assert payload["order_submitted"] is True
    assert payload["recommendation_snapshot_date"] == "2026-04-21"
    assert payload["position_pct"] == 0.12
    assert payload["quantity"] == 1200


def test_auto_trade_strategy_blocks_expired_recommendation_snapshot(db, client, monkeypatch) -> None:
    _seed_recommendation(db, "sh600519", snapshot_at=datetime(2026, 4, 20, 9, 0, tzinfo=UTC))
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 120.0,
            "position_pct": 0.15,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
        now=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "过期推荐阻断策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.15, "intraday_timing_enabled": False},
        },
    ).json()

    payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()

    assert payload["order_submitted"] is False
    assert payload["reason"] == "recommendation_snapshot_expired"
    assert payload["execution_blockers"] == ["recommendation_snapshot_expired"]
    assert payload["recommendation_snapshot_date"] is None


def test_auto_trade_buy_allows_one_add_and_caps_total_position_to_target(db, client, monkeypatch) -> None:
    _seed_recommendation(db, "sh600519", position_pct=15.0, snapshot_at=datetime(2026, 4, 22, 9, 0, tzinfo=UTC))
    buy_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )
    assert buy_response.status_code == 200

    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 118.0,
            "position_pct": 0.15,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
        now=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "允许一次补仓策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.15, "intraday_timing_enabled": False},
        },
    ).json()

    payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()
    assert payload["order_submitted"] is True
    assert payload["reason"] == "order_submitted"
    assert payload["position_add_path"] == "first_add"
    assert payload["quantity"] == 1300

    position = db.scalar(select(Position).where(Position.symbol == "sh600519"))
    assert position is not None
    assert position.quantity == 1400
    assert position.strategy_add_count == 1
    assert str(position.stop_loss_price) == "95.0000"
    assert str(position.take_profit_price) == "118.0000"


def test_auto_trade_buy_blocks_second_add_after_first_strategy_add(db, client, monkeypatch) -> None:
    _seed_recommendation(db, "sh600519", position_pct=15.0, snapshot_at=datetime(2026, 4, 22, 9, 0, tzinfo=UTC))
    buy_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )
    assert buy_response.status_code == 200

    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 118.0,
            "position_pct": 0.15,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
        now=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "禁止第二次补仓策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.15, "intraday_timing_enabled": False},
        },
    ).json()

    first_add_payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()
    assert first_add_payload["order_submitted"] is True
    assert first_add_payload["position_add_path"] == "first_add"

    blocked_payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()
    assert blocked_payload["order_submitted"] is False
    assert blocked_payload["reason"] == "blocked_repeat_add"
    assert blocked_payload["execution_blockers"] == ["blocked_repeat_add"]
    assert blocked_payload["position_add_path"] == "blocked_repeat_add"

    position = db.scalar(select(Position).where(Position.symbol == "sh600519"))
    assert position is not None
    assert position.strategy_add_count == 1


def test_auto_trade_buy_can_open_again_after_position_is_closed(db, client, monkeypatch) -> None:
    from app.core.db import SessionLocal

    _seed_recommendation(db, "sh600519", position_pct=10.0, snapshot_at=datetime(2026, 4, 22, 9, 0, tzinfo=UTC))
    _patch_strategy_signal(
        monkeypatch,
        {
            "symbol": "sh600519",
            "strategy": "moving_average",
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 118.0,
            "position_pct": 0.1,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": True,
        },
        now=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
    )
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "清仓后重开策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1, "intraday_timing_enabled": False},
        },
    ).json()

    first_payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()
    assert first_payload["order_submitted"] is True
    assert first_payload["position_add_path"] == "new_position"

    with SessionLocal() as session:
        position = session.scalar(select(Position).where(Position.symbol == "sh600519"))
        assert position is not None
        sell_quantity = position.quantity
        position.last_buy_date = date(2026, 4, 21)
        session.commit()

    sell_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "sell",
            "order_type": "market",
            "quantity": sell_quantity,
            "price": 100,
        },
    )
    assert sell_response.status_code == 200
    assert sell_response.json()["status"] == "accepted"

    with SessionLocal() as session:
        position = session.scalar(select(Position).where(Position.symbol == "sh600519"))
        assert position is not None
        assert position.quantity == 0
        assert position.strategy_add_count == 0
        assert position.stop_loss_price is None
        assert position.take_profit_price is None
        assert position.exit_guard_status == "inactive"

    reopen_payload = client.post(f"/api/v1/strategies/{created['id']}/run").json()
    assert reopen_payload["order_submitted"] is True
    assert reopen_payload["position_add_path"] == "new_position"


def test_rsi_reversal_strategy_emits_explainable_signal() -> None:
    from app.strategy.strategies.rsi_reversal import RsiReversalStrategy
    from app.strategy.contracts import StrategySignal

    closes = [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 8.5, 9.2, 10]
    signal = StrategySignal.coerce(RsiReversalStrategy().evaluate("sh600000", _build_bars("sh600000", closes), {"rsi_period": 6, "oversold": 35, "position_pct": 0.2})).to_legacy()

    assert signal["strategy"] == "rsi_reversal"
    assert signal["signal"] in {"buy", "hold", "reduce", "sell"}
    assert "rsi" in signal
    assert "trigger_reason" in signal


def test_bollinger_band_strategy_emits_band_values() -> None:
    from app.strategy.strategies.bollinger_band import BollingerBandStrategy

    closes = [10, 10.2, 10.1, 10.3, 10.2, 10.4, 10.3, 10.5, 9.5, 10.1]
    signal = _legacy_signal(BollingerBandStrategy().evaluate("sh600000", _build_bars("sh600000", closes), {"boll_period": 5, "stddev_multiplier": 2}))

    assert signal["strategy"] == "bollinger_band"
    assert "boll_upper" in signal
    assert "boll_middle" in signal
    assert "boll_lower" in signal


def test_signal_fusion_exposes_component_signals() -> None:
    from app.strategy.strategies.signal_fusion import SignalFusionStrategy

    closes = [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 8.5, 9.2, 10, 10.4, 10.8, 11.0, 11.2, 11.4]
    signal = _legacy_signal(SignalFusionStrategy().evaluate("sh600000", _build_bars("sh600000", closes), {}))

    assert signal["strategy"] == "signal_fusion"
    assert signal["signal"] in {"buy", "hold", "reduce", "sell"}
    assert isinstance(signal["component_signals"], list)
    assert signal["component_signals"]
    assert "fusion_score" in signal


def test_strategy_create_accepts_phase7_strategy_type(client) -> None:
    response = client.post(
        "/api/v1/strategies",
        json={
            "name": "RSI 观察",
            "symbol": "sh600036",
            "strategy_type": "rsi_reversal",
            "execution_mode": "signal_only",
            "parameters": {"rsi_period": 14, "oversold": 30, "overbought": 70, "position_pct": 0.1},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_type"] == "rsi_reversal"
    assert payload["parameters"]["rsi_period"] == 14


def test_strategy_create_rejects_invalid_fusion_component(client) -> None:
    response = client.post(
        "/api/v1/strategies",
        json={
            "name": "非法融合",
            "symbol": "sh600036",
            "strategy_type": "signal_fusion",
            "execution_mode": "signal_only",
            "parameters": {"components": [{"strategy_type": "macd", "weight": 1, "parameters": {}}]},
        },
    )

    assert response.status_code == 422
    assert "unsupported fusion component: macd" in response.json()["detail"]["errors"]
