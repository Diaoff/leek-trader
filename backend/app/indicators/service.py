from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Callable

from app.market.providers.base import DailyBarSnapshot


@dataclass(frozen=True, slots=True)
class IndicatorPoint:
    value: float | None
    series: list[float | None]
    insufficient: bool = False
    status: str = "ok"


@dataclass(frozen=True, slots=True)
class BollingerBands:
    upper: float | None
    middle: float | None
    lower: float | None
    series: list[dict[str, float | None]]
    insufficient: bool = False
    status: str = "ok"


@dataclass(frozen=True, slots=True)
class KDJResult:
    k: float | None
    d: float | None
    j: float | None
    series: list[dict[str, float | None]]
    insufficient: bool = False
    status: str = "ok"


@dataclass(frozen=True, slots=True)
class BiasResult:
    bias1: float | None
    bias2: float | None
    bias3: float | None
    series: list[dict[str, float | None]]
    insufficient: bool = False
    status: str = "ok"


@dataclass(frozen=True, slots=True)
class WilliamsRResult:
    wr1: float | None
    wr2: float | None
    series: list[dict[str, float | None]]
    insufficient: bool = False
    status: str = "ok"


@dataclass(frozen=True, slots=True)
class BarSeries:
    closes: list[float]
    highs: list[float]
    lows: list[float]
    volumes: list[float]


class IndicatorService:
    @staticmethod
    def from_bars(bars: list[DailyBarSnapshot]) -> BarSeries:
        return BarSeries(
            closes=[float(bar.close_price) for bar in bars],
            highs=[float(bar.high_price) for bar in bars],
            lows=[float(bar.low_price) for bar in bars],
            volumes=[float(getattr(bar, "volume", 0) or 0) for bar in bars],
        )

    @staticmethod
    def rsi(values: list[float], period: int = 14) -> IndicatorPoint:
        if period < 1 or len(values) <= period:
            return IndicatorPoint(None, [None for _ in values], True, "insufficient_history")

        series: list[float | None] = [None for _ in values]
        gains: list[float] = []
        losses: list[float] = []
        for index in range(1, period + 1):
            change = values[index] - values[index - 1]
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))

        average_gain = sum(gains) / period
        average_loss = sum(losses) / period
        series[period] = IndicatorService._rsi_value(average_gain, average_loss)

        for index in range(period + 1, len(values)):
            change = values[index] - values[index - 1]
            gain = max(change, 0.0)
            loss = max(-change, 0.0)
            average_gain = ((average_gain * (period - 1)) + gain) / period
            average_loss = ((average_loss * (period - 1)) + loss) / period
            series[index] = IndicatorService._rsi_value(average_gain, average_loss)
        return IndicatorPoint(series[-1], series, False, "ok")

    @staticmethod
    def boll(values: list[float], period: int = 20, stddev_multiplier: float = 2.0) -> BollingerBands:
        series: list[dict[str, float | None]] = []
        if period < 1:
            return BollingerBands(None, None, None, [], True, "invalid_period")
        for index in range(len(values)):
            if index + 1 < period:
                series.append({"upper": None, "middle": None, "lower": None})
                continue
            window = values[index + 1 - period:index + 1]
            middle = sum(window) / period
            variance = sum((value - middle) ** 2 for value in window) / period
            stddev = math.sqrt(variance)
            series.append({
                "upper": middle + stddev_multiplier * stddev,
                "middle": middle,
                "lower": middle - stddev_multiplier * stddev,
            })
        if not series or series[-1]["middle"] is None:
            return BollingerBands(None, None, None, series, True, "insufficient_history")
        latest = series[-1]
        return BollingerBands(latest["upper"], latest["middle"], latest["lower"], series, False, "ok")

    @staticmethod
    def kdj(highs: list[float], lows: list[float], closes: list[float], period: int = 9, k_smoothing: int = 3, d_smoothing: int = 3) -> KDJResult:
        length = min(len(highs), len(lows), len(closes))
        series: list[dict[str, float | None]] = [{"k": None, "d": None, "j": None} for _ in range(length)]
        if period < 1 or k_smoothing < 1 or d_smoothing < 1 or length < period:
            return KDJResult(None, None, None, series, True, "insufficient_history")

        k_value = 50.0
        d_value = 50.0
        for index in range(period - 1, length):
            high = max(highs[index + 1 - period:index + 1])
            low = min(lows[index + 1 - period:index + 1])
            rsv = 50.0 if high == low else (closes[index] - low) / (high - low) * 100
            k_value = ((k_smoothing - 1) * k_value + rsv) / k_smoothing
            d_value = ((d_smoothing - 1) * d_value + k_value) / d_smoothing
            j_value = 3 * k_value - 2 * d_value
            series[index] = {"k": k_value, "d": d_value, "j": j_value}
        latest = series[-1]
        return KDJResult(latest["k"], latest["d"], latest["j"], series, False, "ok")

    @staticmethod
    def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> IndicatorPoint:
        length = min(len(highs), len(lows), len(closes))
        if period < 1 or length <= period:
            return IndicatorPoint(None, [None for _ in range(length)], True, "insufficient_history")
        true_ranges: list[float] = []
        for index in range(length):
            if index == 0:
                true_ranges.append(highs[index] - lows[index])
            else:
                previous_close = closes[index - 1]
                true_ranges.append(max(highs[index] - lows[index], abs(highs[index] - previous_close), abs(lows[index] - previous_close)))
        series: list[float | None] = [None for _ in range(length)]
        atr_value = sum(true_ranges[1:period + 1]) / period
        series[period] = atr_value
        for index in range(period + 1, length):
            atr_value = ((atr_value * (period - 1)) + true_ranges[index]) / period
            series[index] = atr_value
        return IndicatorPoint(series[-1], series, False, "ok")

    @staticmethod
    def obv(closes: list[float], volumes: list[float]) -> IndicatorPoint:
        length = min(len(closes), len(volumes))
        if length == 0:
            return IndicatorPoint(None, [], True, "empty_input")
        series: list[float | None] = [0.0]
        obv_value = 0.0
        for index in range(1, length):
            if closes[index] > closes[index - 1]:
                obv_value += volumes[index]
            elif closes[index] < closes[index - 1]:
                obv_value -= volumes[index]
            series.append(obv_value)
        return IndicatorPoint(series[-1], series, False, "ok")

    @staticmethod
    def bias(values: list[float], short_period: int = 6, medium_period: int = 12, long_period: int = 24) -> BiasResult:
        periods = (short_period, medium_period, long_period)
        if any(period < 1 for period in periods):
            return BiasResult(None, None, None, [], True, "invalid_period")
        series: list[dict[str, float | None]] = []
        for index, close in enumerate(values):
            row: dict[str, float | None] = {}
            for key, period in zip(("bias1", "bias2", "bias3"), periods):
                average = IndicatorService._window_average(values, index, period)
                row[key] = None if average is None or average == 0 else (close - average) / average * 100
            series.append(row)
        if not series or any(series[-1][key] is None for key in ("bias1", "bias2", "bias3")):
            return BiasResult(None, None, None, series, True, "insufficient_history")
        latest = series[-1]
        return BiasResult(latest["bias1"], latest["bias2"], latest["bias3"], series, False, "ok")

    @staticmethod
    def williams_r(closes: list[float], highs: list[float], lows: list[float], period: int = 10, short_period: int = 6) -> WilliamsRResult:
        length = min(len(closes), len(highs), len(lows))
        if period < 1 or short_period < 1:
            return WilliamsRResult(None, None, [], True, "invalid_period")
        series: list[dict[str, float | None]] = []
        for index in range(length):
            series.append({
                "wr1": IndicatorService._williams_r_value(closes, highs, lows, index, period),
                "wr2": IndicatorService._williams_r_value(closes, highs, lows, index, short_period),
            })
        if not series or series[-1]["wr1"] is None or series[-1]["wr2"] is None:
            return WilliamsRResult(None, None, series, True, "insufficient_history")
        latest = series[-1]
        return WilliamsRResult(latest["wr1"], latest["wr2"], series, False, "ok")

    @staticmethod
    def cci(closes: list[float], highs: list[float], lows: list[float], period: int = 14) -> IndicatorPoint:
        length = min(len(closes), len(highs), len(lows))
        if period < 1:
            return IndicatorPoint(None, [], True, "invalid_period")
        typical_prices = [(highs[index] + lows[index] + closes[index]) / 3 for index in range(length)]
        series: list[float | None] = []
        for index, typical_price in enumerate(typical_prices):
            average = IndicatorService._window_average(typical_prices, index, period)
            if average is None:
                series.append(None)
                continue
            mean_deviation = sum(abs(value - average) for value in typical_prices[index + 1 - period:index + 1]) / period
            series.append(None if mean_deviation == 0 else (typical_price - average) / (0.015 * mean_deviation))
        if not series or series[-1] is None:
            return IndicatorPoint(None, series, True, "insufficient_history")
        return IndicatorPoint(series[-1], series, False, "ok")

    @staticmethod
    def bbi(values: list[float], period1: int = 3, period2: int = 6, period3: int = 12, period4: int = 20) -> IndicatorPoint:
        periods = (period1, period2, period3, period4)
        if any(period < 1 for period in periods):
            return IndicatorPoint(None, [], True, "invalid_period")
        series: list[float | None] = []
        for index in range(len(values)):
            averages = [IndicatorService._window_average(values, index, period) for period in periods]
            series.append(None if any(average is None for average in averages) else sum(float(average) for average in averages) / len(averages))
        if not series or series[-1] is None:
            return IndicatorPoint(None, series, True, "insufficient_history")
        return IndicatorPoint(series[-1], series, False, "ok")

    @staticmethod
    def ref(values: list[float], period: int = 1) -> list[float | None]:
        if period < 0:
            raise ValueError("period must be non-negative")
        if period == 0:
            return [float(value) for value in values]
        return [None for _ in range(min(period, len(values)))] + [float(value) for value in values[:-period]]

    @staticmethod
    def hhv(values: list[float], period: int) -> list[float | None]:
        return IndicatorService._rolling(values, period, max)

    @staticmethod
    def llv(values: list[float], period: int) -> list[float | None]:
        return IndicatorService._rolling(values, period, min)

    @staticmethod
    def cross(series1: list[float | None], series2: list[float | None]) -> list[bool]:
        length = min(len(series1), len(series2))
        result = [False for _ in range(length)]
        for index in range(1, length):
            prev1, prev2 = series1[index - 1], series2[index - 1]
            curr1, curr2 = series1[index], series2[index]
            if prev1 is None or prev2 is None or curr1 is None or curr2 is None:
                continue
            result[index] = prev1 <= prev2 and curr1 > curr2
        return result

    @staticmethod
    def count(conditions: list[bool], period: int) -> list[int | None]:
        if period < 1:
            return []
        result: list[int | None] = []
        for index in range(len(conditions)):
            if index + 1 < period:
                result.append(None)
            else:
                result.append(sum(1 for item in conditions[index + 1 - period:index + 1] if item))
        return result

    @staticmethod
    def every(conditions: list[bool], period: int) -> list[bool | None]:
        counts = IndicatorService.count(conditions, period)
        return [None if item is None else item == period for item in counts]

    @staticmethod
    def sma(values: list[float], period: int, weight: int = 1) -> list[float | None]:
        if period < 1 or weight < 1:
            return []
        series: list[float | None] = []
        previous: float | None = None
        for value in values:
            numeric = float(value)
            previous = numeric if previous is None else (weight * numeric + (period - weight) * previous) / period
            series.append(previous)
        return series

    @staticmethod
    def _rsi_value(average_gain: float, average_loss: float) -> float:
        if average_loss == 0:
            return 100.0 if average_gain > 0 else 50.0
        relative_strength = average_gain / average_loss
        return 100 - (100 / (1 + relative_strength))

    @staticmethod
    def _window_average(values: list[float], index: int, period: int) -> float | None:
        if period < 1 or index + 1 < period:
            return None
        return sum(values[index + 1 - period:index + 1]) / period

    @staticmethod
    def _rolling(values: list[float], period: int, func: Callable[[list[float]], float]) -> list[float | None]:
        if period < 1:
            return []
        result: list[float | None] = []
        for index in range(len(values)):
            if index + 1 < period:
                result.append(None)
            else:
                result.append(float(func(values[index + 1 - period:index + 1])))
        return result

    @staticmethod
    def _williams_r_value(closes: list[float], highs: list[float], lows: list[float], index: int, period: int) -> float | None:
        if index + 1 < period:
            return None
        highest_high = max(highs[index + 1 - period:index + 1])
        lowest_low = min(lows[index + 1 - period:index + 1])
        spread = highest_high - lowest_low
        return None if spread == 0 else (highest_high - closes[index]) / spread * 100
