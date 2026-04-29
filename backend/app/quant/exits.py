from __future__ import annotations

from app.market.providers.base import DailyBarSnapshot


class RLExitLevelAdvisor:
    version = "rl_exit_advisor_v1"

    def __init__(self, *, stop_loss_floor_pct: float = 0.05, take_profit_rr: float = 2.0, min_risk_reward_ratio: float = 1.0) -> None:
        self.stop_loss_floor_pct = max(0.01, min(stop_loss_floor_pct, 0.3))
        self.take_profit_rr = max(take_profit_rr, min_risk_reward_ratio)
        self.min_risk_reward_ratio = min_risk_reward_ratio

    def advise(
        self,
        *,
        entry_price: float,
        current_price: float,
        bars: list[DailyBarSnapshot],
        holding_days: int = 0,
        max_unrealized_return_pct: float = 0.0,
    ) -> dict[str, object]:
        volatility_pct = self._volatility_pct(bars)
        trend_strength = self._trend_strength(bars)
        current_return_pct = 0.0 if entry_price <= 0 else (current_price - entry_price) / entry_price
        effective_max_return = max(max_unrealized_return_pct, current_return_pct)
        stop_distance_pct = self.stop_loss_floor_pct + min(volatility_pct / 100 * 1.5, 0.12)
        if volatility_pct < 2.0:
            stop_distance_pct *= 0.8
        if trend_strength > 0.03:
            stop_distance_pct *= 1.1
        if holding_days >= 20:
            stop_distance_pct *= 0.9
        stop_price = entry_price * (1 - stop_distance_pct)
        if effective_max_return > 0.08:
            protected_return = effective_max_return * 0.45
            stop_price = max(stop_price, entry_price * (1 + protected_return))
        stop_price = min(stop_price, current_price * 0.995, entry_price * 0.999)
        risk_per_share = max(entry_price - stop_price, entry_price * 0.005)
        rr = max(self.take_profit_rr, self.min_risk_reward_ratio)
        take_profit_price = max(entry_price + risk_per_share * rr, entry_price * 1.01)
        actual_rr = (take_profit_price - entry_price) / risk_per_share if risk_per_share else rr
        return {
            "suggested_stop_loss_price": round(stop_price, 2),
            "suggested_take_profit_price": round(take_profit_price, 2),
            "risk_reward_ratio": round(actual_rr, 6),
            "exit_advice_reason": self._reason(volatility_pct=volatility_pct, trend_strength=trend_strength, max_return=effective_max_return),
            "exit_advice_version": self.version,
        }

    @staticmethod
    def _volatility_pct(bars: list[DailyBarSnapshot]) -> float:
        closes = [float(bar.close_price) for bar in bars if float(bar.close_price or 0) > 0]
        if len(closes) < 2:
            return 0.0
        returns = [(closes[index] - closes[index - 1]) / closes[index - 1] for index in range(1, len(closes))]
        recent = returns[-min(20, len(returns)) :]
        mean = sum(recent) / len(recent)
        return (sum((item - mean) ** 2 for item in recent) / len(recent)) ** 0.5 * 100

    @staticmethod
    def _trend_strength(bars: list[DailyBarSnapshot]) -> float:
        closes = [float(bar.close_price) for bar in bars]
        if len(closes) < 20:
            return 0.0
        short_average = sum(closes[-5:]) / 5
        long_average = sum(closes[-20:]) / 20
        return 0.0 if long_average <= 0 else (short_average - long_average) / long_average

    @staticmethod
    def _reason(*, volatility_pct: float, trend_strength: float, max_return: float) -> str:
        labels = []
        labels.append("high_volatility_wide_stop" if volatility_pct >= 4.0 else "low_volatility_tight_stop")
        if trend_strength > 0.03:
            labels.append("positive_trend_allows_room")
        if max_return > 0.08:
            labels.append("protect_unrealized_profit")
        return "+".join(labels)
