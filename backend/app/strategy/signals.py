from __future__ import annotations

from typing import Any

from app.strategy.contracts import StrategySignal


def clamp_fraction(value: object, *, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(numeric, 1.0))


def hold_signal(symbol: str, strategy: str, *, reason: str, entry_price_ref: float | None = None, market_regime: str = "neutral") -> dict[str, object]:
    return {
        "symbol": symbol,
        "strategy": strategy,
        "signal": "hold",
        "strength": "weak",
        "trigger_reason": reason,
        "entry_price_ref": entry_price_ref,
        "stop_loss_price": None,
        "take_profit_price": None,
        "position_pct": 0.0,
        "market_regime": market_regime,
        "requires_recommendation_confirmation": False,
        "filter_passed": True,
        "filter_reasons": [],
        "trend_ok": None,
        "volume_ok": None,
        "volatility_ok": None,
        "stretch_ok": None,
        "market_regime_bias": None,
    }


def signal_from_payload(payload: dict[str, Any]) -> StrategySignal:
    return StrategySignal.coerce(payload)


def hold_strategy_signal(
    symbol: str,
    strategy: str,
    *,
    reason: str,
    entry_price_ref: float | None = None,
    market_regime: str = "neutral",
) -> StrategySignal:
    return signal_from_payload(
        hold_signal(
            symbol,
            strategy,
            reason=reason,
            entry_price_ref=entry_price_ref,
            market_regime=market_regime,
        )
    )


def risk_prices(latest_close: float, signal: str, *, stop_loss_pct: float = 0.05, take_profit_pct: float = 0.1) -> tuple[float | None, float | None]:
    if signal == "hold":
        return None, None
    stop_loss_price = round(latest_close * (1 - stop_loss_pct), 2)
    take_profit_price = round(latest_close * (1 + take_profit_pct), 2)
    return stop_loss_price, take_profit_price
