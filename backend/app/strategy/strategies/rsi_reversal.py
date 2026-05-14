from __future__ import annotations

from app.indicators.service import IndicatorService
from app.market.providers.base import DailyBarSnapshot
from app.strategy.base import StrategyPlugin
from app.strategy.contracts import ParameterConstraint, RiskIntent, StrategyMetadata, StrategySignal
from app.strategy.signals import clamp_fraction, hold_signal, risk_prices


class RsiReversalStrategy(StrategyPlugin):
    name = "rsi_reversal"
    metadata = StrategyMetadata(
        strategy_type=name,
        display_name="RSI 反转",
        template_category="mean_reversion",
        minimum_history=20,
        supported_execution_modes=("signal_only",),
        parameter_schema=(
            ParameterConstraint("rsi_period", "integer", minimum=2, default=14, description="RSI 周期"),
            ParameterConstraint("oversold", "number", minimum=0, maximum=100, default=30, description="超卖阈值"),
            ParameterConstraint("overbought", "number", minimum=0, maximum=100, default=70, description="超买阈值"),
            ParameterConstraint("position_pct", "number", minimum=0, maximum=1, default=0.1, description="最大仓位"),
        ),
        risk_note="单一震荡指标容易逆势接刀，需结合趋势和仓位控制",
        mode_note="适合观察超买超卖后的反转信号，默认仅信号观察",
        auto_trade_allowed=False,
    )

    def minimum_history(self, parameters: dict[str, object]) -> int:
        return max(int(parameters.get("rsi_period", 14)) + 10, self.metadata.minimum_history)

    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> dict[str, object] | StrategySignal:
        period = max(int(parameters.get("rsi_period", 14)), 2)
        oversold = float(parameters.get("oversold", 30))
        overbought = float(parameters.get("overbought", 70))
        position_pct = clamp_fraction(parameters.get("position_pct", 0.1), default=0.1)
        closes = [float(bar.close_price) for bar in bars]
        if len(closes) <= period:
            return hold_signal(symbol, self.name, reason="insufficient_history", entry_price_ref=round(closes[-1], 2) if closes else None)

        rsi = IndicatorService.rsi(closes, period)
        rsi_now = rsi.value
        rsi_prev = next((value for value in reversed(rsi.series[:-1]) if value is not None), None)
        latest_close = closes[-1]
        if rsi_now is None:
            return hold_signal(symbol, self.name, reason="rsi_unavailable", entry_price_ref=round(latest_close, 2))

        signal = "hold"
        strength = "weak"
        reason = "rsi_neutral"
        target_position = 0.0
        if rsi_prev is not None and rsi_prev <= oversold < rsi_now:
            signal = "buy"
            strength = "strong" if rsi_now >= oversold + 5 else "normal"
            reason = "rsi_oversold_rebound"
            target_position = position_pct
        elif rsi_now <= oversold:
            signal = "buy"
            strength = "weak"
            reason = "rsi_oversold_watch"
            target_position = min(position_pct, 0.08)
        elif rsi_prev is not None and rsi_prev >= overbought > rsi_now:
            signal = "sell"
            strength = "normal"
            reason = "rsi_overbought_rollover"
            target_position = 1.0
        elif rsi_now >= overbought:
            signal = "reduce"
            strength = "weak"
            reason = "rsi_overbought_watch"
            target_position = 0.5

        stop_loss_price, take_profit_price = risk_prices(latest_close, signal)
        return StrategySignal(
            symbol=symbol,
            strategy=self.name,
            action=signal,  # type: ignore[arg-type]
            strength=strength,
            trigger_reason=reason,
            position_pct=target_position,
            risk_intent=RiskIntent(
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                requires_confirmation=signal == "buy",
            ),
            metadata={
                "entry_price_ref": round(latest_close, 2),
                "market_regime": "oversold" if rsi_now <= oversold else "overbought" if rsi_now >= overbought else "neutral",
                "rsi": round(rsi_now, 4),
                "previous_rsi": round(rsi_prev, 4) if rsi_prev is not None else None,
                "oversold": oversold,
                "overbought": overbought,
                "filter_passed": True,
                "filter_reasons": [],
            },
        )
