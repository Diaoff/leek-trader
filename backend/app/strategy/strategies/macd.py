from __future__ import annotations

from app.market.providers.base import DailyBarSnapshot
from app.strategy.base import StrategyPlugin


class MacdStrategy(StrategyPlugin):
    name = "macd"

    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> dict[str, object]:
        fast_period = max(int(parameters.get("fast_period", 12)), 2)
        slow_period = max(int(parameters.get("slow_period", 26)), fast_period + 1)
        signal_period = max(int(parameters.get("signal_period", 9)), 2)
        base_position_pct = self._clamp_fraction(parameters.get("position_pct"), default=0.1)

        minimum_bars = slow_period + signal_period + 6
        if len(bars) < minimum_bars:
            return self._build_hold_signal(symbol, reason="insufficient_history", entry_price_ref=self._last_close(bars))

        closes = [float(bar.close_price) for bar in bars]
        ema_fast = self._ema_series(closes, fast_period)
        ema_slow = self._ema_series(closes, slow_period)
        dif_series = [fast - slow for fast, slow in zip(ema_fast, ema_slow)]
        dea_series = self._ema_series(dif_series, signal_period)
        hist_series = [(dif - dea) * 2 for dif, dea in zip(dif_series, dea_series)]

        dif_now = dif_series[-1]
        dif_prev = dif_series[-2]
        dea_now = dea_series[-1]
        dea_prev = dea_series[-2]
        hist_now = hist_series[-1]
        hist_prev = hist_series[-2]
        hist_prev2 = hist_series[-3]
        latest_close = closes[-1]

        signal = "hold"
        strength = "weak"
        trigger_reason = "macd_waiting"
        position_pct = 0.0

        golden_cross = dif_prev <= dea_prev and dif_now > dea_now
        death_cross = dif_prev >= dea_prev and dif_now < dea_now

        if golden_cross:
            signal = "buy"
            strength = "strong" if dif_now > 0 and dea_now > 0 else "normal" if hist_now > hist_prev else "weak"
            trigger_reason = "macd_golden_cross_above_zero" if dif_now > 0 and dea_now > 0 else "macd_golden_cross_below_zero"
            position_pct = base_position_pct if strength == "strong" else min(base_position_pct, 0.1)
        elif death_cross and dif_now < 0:
            signal = "sell"
            strength = "strong"
            trigger_reason = "macd_death_cross_below_zero"
            position_pct = 1.0
        elif death_cross:
            signal = "reduce"
            strength = "normal"
            trigger_reason = "macd_death_cross_above_zero"
            position_pct = 0.5
        elif dif_now > 0 and hist_now > hist_prev > hist_prev2:
            signal = "buy"
            strength = "normal"
            trigger_reason = "macd_histogram_expanding"
            position_pct = min(base_position_pct, 0.1)
        elif dif_now > 0 and hist_now < hist_prev and hist_prev >= hist_prev2:
            signal = "reduce"
            strength = "weak"
            trigger_reason = "macd_histogram_contracting"
            position_pct = 0.5
        elif dif_now < 0 and hist_now < hist_prev < hist_prev2:
            signal = "sell"
            strength = "normal"
            trigger_reason = "macd_below_zero_weakening"
            position_pct = 1.0

        market_regime = self._market_regime(dif_now, dea_now, hist_now)
        stop_loss_price = round(latest_close * (0.95 if signal == "buy" else 0.97), 2) if signal in {"buy", "reduce"} else round(latest_close * 0.985, 2)
        take_profit_price = round(max(latest_close * 1.1, latest_close + (latest_close - stop_loss_price) * 2), 2)

        return {
            "symbol": symbol,
            "strategy": self.name,
            "signal": signal,
            "strength": strength,
            "trigger_reason": trigger_reason,
            "entry_price_ref": round(latest_close, 2),
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "position_pct": position_pct,
            "market_regime": market_regime,
            "requires_recommendation_confirmation": signal == "buy",
            "dif": round(dif_now, 4),
            "dea": round(dea_now, 4),
            "histogram": round(hist_now, 4),
            "previous_dif": round(dif_prev, 4),
            "previous_dea": round(dea_prev, 4),
            "previous_histogram": round(hist_prev, 4),
        }

    @staticmethod
    def _ema_series(values: list[float], period: int) -> list[float]:
        multiplier = 2 / (period + 1)
        ema_values: list[float] = []
        ema = values[0]
        for value in values:
            ema = (value - ema) * multiplier + ema
            ema_values.append(ema)
        return ema_values

    @staticmethod
    def _market_regime(dif_value: float, dea_value: float, histogram: float) -> str:
        if dif_value > 0 and dea_value > 0 and histogram > 0:
            return "bullish"
        if dif_value < 0 and dea_value < 0 and histogram < 0:
            return "bearish"
        return "neutral"

    @staticmethod
    def _build_hold_signal(symbol: str, *, reason: str, entry_price_ref: float | None) -> dict[str, object]:
        return {
            "symbol": symbol,
            "strategy": "macd",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": reason,
            "entry_price_ref": entry_price_ref,
            "stop_loss_price": None,
            "take_profit_price": None,
            "position_pct": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
        }

    @staticmethod
    def _last_close(bars: list[DailyBarSnapshot]) -> float | None:
        return round(float(bars[-1].close_price), 2) if bars else None

    @staticmethod
    def _clamp_fraction(value: object, *, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(numeric, 1.0))
