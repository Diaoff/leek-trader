from __future__ import annotations

from app.indicators.service import IndicatorService
from app.market.providers.base import DailyBarSnapshot
from app.strategy.base import StrategyPlugin
from app.strategy.contracts import ParameterConstraint, StrategyMetadata, StrategySignal
from app.strategy.signals import clamp_fraction, hold_strategy_signal, risk_prices, signal_from_payload


class KdjMomentumStrategy(StrategyPlugin):
    name = "kdj_momentum"
    metadata = StrategyMetadata(
        strategy_type=name,
        display_name="KDJ 动量",
        template_category="momentum",
        minimum_history=20,
        supported_execution_modes=("signal_only",),
        parameter_schema=(
            ParameterConstraint("kdj_period", "integer", minimum=2, default=9, description="KDJ 周期"),
            ParameterConstraint("k_smoothing", "integer", minimum=1, default=3, description="K 平滑"),
            ParameterConstraint("d_smoothing", "integer", minimum=1, default=3, description="D 平滑"),
            ParameterConstraint("position_pct", "number", minimum=0, maximum=1, default=0.1, description="最大仓位"),
        ),
        risk_note="高频交叉容易产生噪音，需先纸面验证",
        mode_note="适合观察 K/D 交叉与短线动量变化",
        auto_trade_allowed=False,
    )

    def minimum_history(self, parameters: dict[str, object]) -> int:
        return max(int(parameters.get("kdj_period", 9)) + 10, self.metadata.minimum_history)

    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> StrategySignal:
        period = max(int(parameters.get("kdj_period", 9)), 2)
        k_smoothing = max(int(parameters.get("k_smoothing", 3)), 1)
        d_smoothing = max(int(parameters.get("d_smoothing", 3)), 1)
        position_pct = clamp_fraction(parameters.get("position_pct", 0.1), default=0.1)
        series = IndicatorService.from_bars(bars)
        if len(series.closes) < period:
            return hold_strategy_signal(symbol, self.name, reason="insufficient_history", entry_price_ref=round(series.closes[-1], 2) if series.closes else None)

        kdj = IndicatorService.kdj(series.highs, series.lows, series.closes, period, k_smoothing, d_smoothing)
        latest_close = series.closes[-1]
        previous = next((item for item in reversed(kdj.series[:-1]) if item.get("k") is not None and item.get("d") is not None), None)
        if kdj.k is None or kdj.d is None or kdj.j is None:
            return hold_strategy_signal(symbol, self.name, reason="kdj_unavailable", entry_price_ref=round(latest_close, 2))

        signal = "hold"
        strength = "weak"
        reason = "kdj_waiting"
        target_position = 0.0
        previous_k = float(previous["k"]) if previous and previous.get("k") is not None else None
        previous_d = float(previous["d"]) if previous and previous.get("d") is not None else None
        golden_cross = previous_k is not None and previous_d is not None and previous_k <= previous_d and kdj.k > kdj.d
        death_cross = previous_k is not None and previous_d is not None and previous_k >= previous_d and kdj.k < kdj.d
        if golden_cross and kdj.k < 35:
            signal = "buy"
            strength = "strong"
            reason = "kdj_low_golden_cross"
            target_position = position_pct
        elif golden_cross:
            signal = "buy"
            strength = "normal"
            reason = "kdj_golden_cross"
            target_position = min(position_pct, 0.08)
        elif death_cross and kdj.k > 65:
            signal = "sell"
            strength = "normal"
            reason = "kdj_high_death_cross"
            target_position = 1.0
        elif death_cross:
            signal = "reduce"
            strength = "weak"
            reason = "kdj_death_cross"
            target_position = 0.5

        stop_loss_price, take_profit_price = risk_prices(latest_close, signal)
        return signal_from_payload({
            "symbol": symbol,
            "strategy": self.name,
            "signal": signal,
            "strength": strength,
            "trigger_reason": reason,
            "entry_price_ref": round(latest_close, 2),
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "position_pct": target_position,
            "market_regime": "bullish" if kdj.k > kdj.d else "bearish" if kdj.k < kdj.d else "neutral",
            "requires_recommendation_confirmation": signal == "buy",
            "kdj_k": round(kdj.k, 4),
            "kdj_d": round(kdj.d, 4),
            "kdj_j": round(kdj.j, 4),
            "previous_kdj_k": round(previous_k, 4) if previous_k is not None else None,
            "previous_kdj_d": round(previous_d, 4) if previous_d is not None else None,
            "filter_passed": True,
            "filter_reasons": [],
        })
