from app.strategy.contracts import StrategyContext, StrategySignal
from app.strategy.plugins import StrategyPluginRegistry


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
    assert signal.to_dict()["legacy"]["signal"] == "buy"


def test_strategy_plugin_metadata_and_context_are_available() -> None:
    plugin = StrategyPluginRegistry().get("moving_average")
    context = plugin.build_context(
        execution_mode="signal_only",
        parameters={"short_window": 5, "long_window": 20, "position_pct": 0.1},
        history_available=35,
    )

    assert plugin.metadata.strategy_type == "moving_average"
    assert plugin.metadata.minimum_history >= 30
    assert "signal_only" in plugin.metadata.supported_execution_modes
    assert context == StrategyContext(
        environment="paper",
        execution_mode="signal_only",
        available_cash=None,
        position_value=None,
        total_equity=None,
        position_symbols=(),
        paper_trading=True,
        backtest=False,
        strategy_parameters={"short_window": 5, "long_window": 20, "position_pct": 0.1},
        minimum_history=30,
        history_ready=True,
        history_available=35,
    )
