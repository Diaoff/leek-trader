from app.strategy.contracts import StrategySignal


def test_strategy_signal_round_trips_legacy_payload() -> None:
    legacy = {
        "symbol": "sh600519",
        "strategy": "moving_average",
        "signal": "buy",
        "strength": "strong",
        "trigger_reason": "golden_cross",
        "position_pct": 0.25,
        "stop_loss_price": 95.0,
        "take_profit_price": 120.0,
        "requires_recommendation_confirmation": True,
        "component_signals": [{"name": "ma"}],
    }

    signal = StrategySignal.from_legacy(legacy)

    assert signal.action == "buy"
    assert signal.order_intent is not None
    assert signal.order_intent.side == "buy"
    assert signal.order_intent.target_position_pct == 0.25
    assert signal.order_intent.reason == "golden_cross"
    assert signal.risk_intent.stop_loss_price == 95.0
    assert signal.risk_intent.take_profit_price == 120.0
    assert signal.risk_intent.requires_confirmation is True
    assert signal.metadata["component_signals"] == [{"name": "ma"}]
    assert signal.to_legacy()["signal"] == "buy"
    assert signal.to_legacy()["component_signals"] == [{"name": "ma"}]
