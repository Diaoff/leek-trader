from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from app.market.providers.base import DailyBarSnapshot
from app.models.smart_selection_item import SmartSelectionItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus
from app.strategy.strategies.macd import MacdStrategy
from app.strategy.strategies.moving_average import MovingAverageStrategy


def _build_bars(symbol: str, closes: list[float]) -> list[DailyBarSnapshot]:
    start = date(2026, 4, 1)
    return [
        DailyBarSnapshot(
            symbol=symbol,
            trade_date=start + timedelta(days=index),
            open_price=close * 0.99,
            close_price=close,
            high_price=close * 1.01,
            low_price=close * 0.98,
            volume=1_000_000 + index * 10_000,
        )
        for index, close in enumerate(closes)
    ]


def _seed_recommendation(db, symbol: str, *, score: float = 82.0, timing: str = "STRONG BUY", position_pct: float = 12.0) -> None:
    run = SmartSelectionRun(
        tenant_id="local",
        status=SmartSelectionRunStatus.SUCCEEDED,
        triggered_by="manual",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        generated_at=datetime.now(UTC),
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
            target_price=118.0,
            stop_loss_price=94.0,
            tags=["strong_buy"],
            reason="测试推荐",
            raw_detail={"timing": timing, "position_pct": position_pct},
        )
    )
    db.commit()


def _patch_strategy_signal(monkeypatch, payload: dict) -> None:
    import app.api.strategies as strategies_api

    monkeypatch.setattr(strategies_api.service, "_evaluate_strategy", lambda strategy: payload)
    monkeypatch.setattr(strategies_api.service, "_is_opening_trade_window", lambda now=None: True)
    monkeypatch.setattr(
        strategies_api.service.trading_service,
        "_get_quote_snapshot",
        lambda symbol: {"price": 100.0, "change_percent": 0.0, "is_halted": False},
    )


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


def test_moving_average_plugin_emits_golden_cross_signal() -> None:
    plugin = MovingAverageStrategy()
    signal = plugin.evaluate(
        "sh600036",
        _build_bars("sh600036", [10, 10, 10, 10, 10, 9, 8, 9, 10, 12]),
        {"short_window": 3, "long_window": 5, "position_pct": 0.12},
    )

    assert signal["signal"] == "buy"
    assert signal["strength"] == "strong"
    assert signal["trigger_reason"] == "golden_cross"


def test_moving_average_plugin_avoids_repeated_buy_on_existing_uptrend() -> None:
    plugin = MovingAverageStrategy()
    signal = plugin.evaluate(
        "sh600036",
        _build_bars("sh600036", [10, 10.2, 10.4, 10.6, 10.8, 11.0, 11.1, 11.15, 11.18, 11.2]),
        {"short_window": 3, "long_window": 5, "position_pct": 0.12},
    )

    assert signal["signal"] == "hold"
    assert signal["trigger_reason"] == "waiting_for_confirmation"


def test_moving_average_plugin_returns_hold_when_history_is_insufficient() -> None:
    plugin = MovingAverageStrategy()
    signal = plugin.evaluate(
        "sh600036",
        _build_bars("sh600036", [10, 10.1, 10.2, 10.3]),
        {"short_window": 3, "long_window": 5},
    )

    assert signal["signal"] == "hold"
    assert signal["trigger_reason"] == "insufficient_history"


def test_macd_plugin_emits_golden_cross_and_death_cross_signals() -> None:
    plugin = MacdStrategy()

    buy_signal = plugin.evaluate(
        "sh600036",
        _build_bars(
            "sh600036",
            [10, 10.2, 10.5, 10.8, 11.1, 11.4, 11.7, 12.0, 12.3, 12.6, 12.9, 13.1, 11.77, 13.04, 13.4, 11.04, 12.18, 12.85],
        ),
        {"fast_period": 4, "slow_period": 8, "signal_period": 3, "position_pct": 0.1},
    )
    sell_signal = plugin.evaluate(
        "sh600036",
        _build_bars(
            "sh600036",
            [10, 10.3, 10.6, 10.9, 11.2, 11.5, 11.8, 12.1, 12.4, 12.7, 13.0, 13.2, 10.36, 9.9, 12.15, 9.84, 12.75, 9.62],
        ),
        {"fast_period": 4, "slow_period": 8, "signal_period": 3, "position_pct": 0.1},
    )

    assert buy_signal["signal"] == "buy"
    assert buy_signal["trigger_reason"] == "macd_golden_cross_above_zero"
    assert buy_signal["strength"] == "strong"
    assert sell_signal["signal"] == "sell"
    assert sell_signal["trigger_reason"] == "macd_death_cross_below_zero"


def test_macd_plugin_distinguishes_zero_axis_strength() -> None:
    plugin = MacdStrategy()

    strong_signal = plugin.evaluate(
        "sh600036",
        _build_bars("sh600036", [10, 10.2, 10.5, 10.8, 11.1, 11.4, 11.7, 12.0, 12.3, 12.6, 12.9, 13.1, 11.77, 13.04, 13.4, 11.04, 12.18, 12.85]),
        {"fast_period": 4, "slow_period": 8, "signal_period": 3, "position_pct": 0.1},
    )
    weak_signal = plugin.evaluate(
        "sh600036",
        _build_bars("sh600036", [15, 14.7, 14.4, 14.1, 13.8, 13.5, 13.2, 12.9, 12.6, 12.3, 12.0, 11.7, 11.69, 12.44, 11.45, 12.79, 11.05, 12.52]),
        {"fast_period": 4, "slow_period": 8, "signal_period": 3, "position_pct": 0.1},
    )

    assert strong_signal["signal"] == "buy"
    assert strong_signal["strength"] == "strong"
    assert strong_signal["trigger_reason"] == "macd_golden_cross_above_zero"
    assert weak_signal["signal"] == "buy"
    assert weak_signal["trigger_reason"] == "macd_golden_cross_below_zero"


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
    assert run_payload["signal"]["signal"] in {"buy", "sell", "reduce", "hold"}
    assert run_payload["execution_mode"] == "auto_trade"
    assert "execution_blockers" in run_payload

    list_response = client.get("/api/v1/strategies")
    refreshed = next(item for item in list_response.json() if item["id"] == created["id"])
    assert refreshed["latest_run_status"] == "success"
    assert refreshed["run_count_today"] == 1
    assert refreshed["total_run_count"] == 1
    assert refreshed["latest_signal"] in {"buy", "sell", "reduce", "hold"}
    assert refreshed["latest_signal_summary"] is not None


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
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.2},
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
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.15},
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


def test_auto_trade_sell_signal_is_blocked_by_t_plus_one(client, monkeypatch) -> None:
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
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.15},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["order_submitted"] is False
    assert payload["reason"] == "t_plus_one_restriction"
    assert payload["execution_blockers"] == ["t_plus_one_restriction"]


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
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.2},
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
