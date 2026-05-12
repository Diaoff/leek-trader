from __future__ import annotations

from app.indicators.service import IndicatorService
from app.market.providers.base import DailyBarSnapshot
from app.strategy.base import StrategyPlugin
from app.strategy.signals import clamp_fraction, hold_signal, risk_prices


class BollingerBandStrategy(StrategyPlugin):
    name = "bollinger_band"

    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> dict[str, object]:
        period = max(int(parameters.get("boll_period", 20)), 2)
        multiplier = max(float(parameters.get("stddev_multiplier", 2)), 0.1)
        position_pct = clamp_fraction(parameters.get("position_pct", 0.1), default=0.1)
        closes = [float(bar.close_price) for bar in bars]
        if len(closes) < period:
            return hold_signal(symbol, self.name, reason="insufficient_history", entry_price_ref=round(closes[-1], 2) if closes else None)

        boll = IndicatorService.boll(closes, period, multiplier)
        latest_close = closes[-1]
        previous_close = closes[-2] if len(closes) >= 2 else latest_close
        previous_band = boll.series[-2] if len(boll.series) >= 2 else {"upper": None, "middle": None, "lower": None}
        if boll.middle is None or boll.upper is None or boll.lower is None:
            return hold_signal(symbol, self.name, reason="boll_unavailable", entry_price_ref=round(latest_close, 2))

        signal = "hold"
        strength = "weak"
        reason = "boll_inside_band"
        target_position = 0.0
        if previous_band.get("lower") is not None and previous_close < float(previous_band["lower"]) and latest_close >= boll.lower:
            signal = "buy"
            strength = "normal"
            reason = "boll_lower_rebound"
            target_position = position_pct
        elif latest_close <= boll.lower:
            signal = "buy"
            strength = "weak"
            reason = "boll_lower_touch"
            target_position = min(position_pct, 0.08)
        elif previous_band.get("upper") is not None and previous_close > float(previous_band["upper"]) and latest_close <= boll.upper:
            signal = "reduce"
            strength = "normal"
            reason = "boll_upper_rollover"
            target_position = 0.5
        elif latest_close >= boll.upper:
            signal = "reduce"
            strength = "weak"
            reason = "boll_upper_touch"
            target_position = 0.5

        stop_loss_price, take_profit_price = risk_prices(latest_close, signal)
        bandwidth = (boll.upper - boll.lower) / boll.middle if boll.middle else 0.0
        return {
            "symbol": symbol,
            "strategy": self.name,
            "signal": signal,
            "strength": strength,
            "trigger_reason": reason,
            "entry_price_ref": round(latest_close, 2),
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "position_pct": target_position,
            "market_regime": "below_band" if latest_close <= boll.lower else "above_band" if latest_close >= boll.upper else "neutral",
            "requires_recommendation_confirmation": signal == "buy",
            "boll_upper": round(boll.upper, 4),
            "boll_middle": round(boll.middle, 4),
            "boll_lower": round(boll.lower, 4),
            "boll_bandwidth": round(bandwidth, 4),
            "filter_passed": True,
            "filter_reasons": [],
        }
