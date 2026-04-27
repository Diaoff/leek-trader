from __future__ import annotations

import math
from dataclasses import dataclass

from app.market.providers.base import DailyBarSnapshot

DEFAULT_VOLUME_CONFIRM_RATIO = 1.05
DEFAULT_MAX_VOLATILITY_20 = 0.08
MAX_BREAKOUT_FROM_RANGE = 0.02
MAX_STRETCH_FROM_MA20 = 0.06
MAX_THREE_DAY_SURGE = 0.07


@dataclass(slots=True)
class ManagerStyleFilterResult:
    filter_passed: bool
    filter_reasons: list[str]
    trend_ok: bool | None
    volume_ok: bool | None
    volatility_ok: bool | None
    stretch_ok: bool | None
    market_regime_bias: str | None


class ManagerStyleGate:
    def __init__(self, bars: list[DailyBarSnapshot], parameters: dict[str, object]) -> None:
        closes = [float(bar.close_price) for bar in bars]
        volumes = [float(bar.volume or 0.0) for bar in bars]

        self.latest_close = closes[-1]
        self.previous_close = closes[-2]
        self.ma20 = self._average(closes[-20:]) if len(closes) >= 20 else None
        self.ma20_prev = self._average(closes[-21:-1]) if len(closes) >= 21 else None
        self.ma60 = self._average(closes[-60:]) if len(closes) >= 60 else None
        self.latest_volume = volumes[-1]
        self.volume_ma20 = self._average(volumes[-20:]) if len(volumes) >= 20 else None
        self.volatility20 = self._volatility20(closes)
        self.recent_high_10 = max(closes[-10:-1]) if len(closes) >= 10 else self.latest_close
        self.recent_low_5 = min(closes[-5:-1]) if len(closes) >= 5 else self.latest_close
        self.three_day_return = (
            (self.latest_close / closes[-4]) - 1 if len(closes) >= 4 and closes[-4] > 0 else 0.0
        )
        self.volume_confirm_ratio = self._coerce_threshold(
            parameters.get("volume_confirm_ratio"),
            default=DEFAULT_VOLUME_CONFIRM_RATIO,
            minimum=0.5,
            maximum=3.0,
        )
        self.max_volatility_20 = self._coerce_threshold(
            parameters.get("max_volatility_20"),
            default=DEFAULT_MAX_VOLATILITY_20,
            minimum=0.01,
            maximum=0.5,
        )

    def evaluate_buy_filter(
        self,
        *,
        raw_trigger_reason: str,
        extra_reasons: list[str] | None = None,
    ) -> ManagerStyleFilterResult:
        trend_ok = self.trend_ok
        volume_ok = self.volume_ok
        volatility_ok = self.volatility_ok
        stretch_ok = self.stretch_ok
        market_regime_bias = self.market_regime_bias

        reasons: list[str] = []
        if trend_ok is False:
            reasons.append("trend_not_confirmed")
        if volume_ok is False:
            reasons.append("volume_not_confirmed")
        if volatility_ok is False:
            reasons.append("volatility_too_high")
        if stretch_ok is False:
            reasons.append("price_too_stretched")
        if market_regime_bias == "defensive":
            reasons.append("market_regime_not_supportive")
        if raw_trigger_reason == "trend_follow_buy" and self.is_mild_trend_extension:
            reasons.append("trend_follow_extension_too_hot")
        if extra_reasons:
            reasons.extend(extra_reasons)

        deduped_reasons = list(dict.fromkeys(reasons))
        return ManagerStyleFilterResult(
            filter_passed=not deduped_reasons,
            filter_reasons=deduped_reasons,
            trend_ok=trend_ok,
            volume_ok=volume_ok,
            volatility_ok=volatility_ok,
            stretch_ok=stretch_ok,
            market_regime_bias=market_regime_bias,
        )

    def diagnostic_result(self) -> ManagerStyleFilterResult:
        return ManagerStyleFilterResult(
            filter_passed=True,
            filter_reasons=[],
            trend_ok=self.trend_ok,
            volume_ok=self.volume_ok,
            volatility_ok=self.volatility_ok,
            stretch_ok=self.stretch_ok,
            market_regime_bias=self.market_regime_bias,
        )

    @property
    def trend_ok(self) -> bool | None:
        if self.ma20 is None or self.ma20_prev is None:
            return None
        return self.latest_close > self.ma20 and self.ma20 > self.ma20_prev

    @property
    def volume_ok(self) -> bool | None:
        if self.volume_ma20 is None or self.volume_ma20 <= 0:
            return None
        return self.latest_volume >= self.volume_ma20 * self.volume_confirm_ratio

    @property
    def volatility_ok(self) -> bool | None:
        if self.volatility20 is None:
            return None
        return self.volatility20 <= self.max_volatility_20

    @property
    def stretch_ok(self) -> bool | None:
        if self.ma20 is None or self.ma20 <= 0:
            return None
        if self._is_overheated():
            return False

        breakout_candidate = (
            self.latest_close >= self.recent_high_10 * 0.995
            and self.latest_close <= self.recent_high_10 * (1 + MAX_BREAKOUT_FROM_RANGE)
            and self.latest_close <= self.ma20 * (1 + MAX_STRETCH_FROM_MA20)
        )
        pullback_repair = (
            self.latest_close >= self.ma20
            and self.recent_low_5 <= self.ma20 * 1.01
            and self.latest_close <= self.recent_high_10 * 1.015
        )
        return breakout_candidate or pullback_repair or self.latest_close <= self.ma20 * 1.04

    @property
    def market_regime_bias(self) -> str | None:
        if self.ma20 is None or self.ma20_prev is None:
            return None
        if (
            self.latest_close < self.ma20 * 0.985
            or self.ma20 <= self.ma20_prev
            or (self.volatility20 is not None and self.volatility20 > self.max_volatility_20 * 1.2)
        ):
            return "defensive"
        if self.ma60 is not None and self.latest_close > self.ma20 > self.ma60 and self.ma20 > self.ma20_prev:
            return "supportive"
        if self.latest_close > self.ma20 and self.ma20 > self.ma20_prev:
            return "neutral"
        return "cautious"

    @property
    def is_mild_trend_extension(self) -> bool:
        if self.ma20 is None or self.ma20 <= 0:
            return False
        return (
            self.latest_close > self.recent_high_10
            and self.latest_close <= self.recent_high_10 * 1.01
            and self.latest_close >= self.ma20 * 1.035
        )

    def apply_to_signal(self, signal: dict[str, object], result: ManagerStyleFilterResult) -> dict[str, object]:
        signal.update(
            {
                "filter_passed": result.filter_passed,
                "filter_reasons": result.filter_reasons,
                "trend_ok": result.trend_ok,
                "volume_ok": result.volume_ok,
                "volatility_ok": result.volatility_ok,
                "stretch_ok": result.stretch_ok,
                "market_regime_bias": result.market_regime_bias,
            }
        )
        return signal

    def suppress_buy_signal(self, signal: dict[str, object], result: ManagerStyleFilterResult) -> dict[str, object]:
        signal.update(
            {
                "signal": "hold",
                "strength": "weak",
                "position_pct": 0.0,
                "requires_recommendation_confirmation": False,
            }
        )
        return self.apply_to_signal(signal, result)

    def _is_overheated(self) -> bool:
        if self.ma20 is None or self.ma20 <= 0:
            return False
        return (
            self.latest_close > self.ma20 * 1.08
            or self.latest_close > self.recent_high_10 * 1.03
            or self.three_day_return > MAX_THREE_DAY_SURGE
        )

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values)

    @staticmethod
    def _coerce_threshold(value: object, *, default: float, minimum: float, maximum: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = default
        return max(minimum, min(numeric, maximum))

    @staticmethod
    def _volatility20(closes: list[float]) -> float | None:
        if len(closes) < 21:
            return None
        returns = [(current / previous) - 1 for previous, current in zip(closes[-21:-1], closes[-20:]) if previous > 0]
        if len(returns) < 2:
            return None
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / len(returns)
        return math.sqrt(variance) * math.sqrt(20)
