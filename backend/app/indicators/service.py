from __future__ import annotations

from dataclasses import dataclass
import math

from app.market.providers.base import DailyBarSnapshot


@dataclass(frozen=True, slots=True)
class IndicatorPoint:
    value: float | None
    series: list[float | None]
    insufficient: bool = False


@dataclass(frozen=True, slots=True)
class BollingerBands:
    upper: float | None
    middle: float | None
    lower: float | None
    series: list[dict[str, float | None]]
    insufficient: bool = False


@dataclass(frozen=True, slots=True)
class KDJResult:
    k: float | None
    d: float | None
    j: float | None
    series: list[dict[str, float | None]]
    insufficient: bool = False


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
            return IndicatorPoint(None, [None for _ in values], True)

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
        return IndicatorPoint(series[-1], series, False)

    @staticmethod
    def boll(values: list[float], period: int = 20, stddev_multiplier: float = 2.0) -> BollingerBands:
        series: list[dict[str, float | None]] = []
        if period < 1:
            return BollingerBands(None, None, None, [], True)
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
            return BollingerBands(None, None, None, series, True)
        latest = series[-1]
        return BollingerBands(latest["upper"], latest["middle"], latest["lower"], series, False)

    @staticmethod
    def kdj(highs: list[float], lows: list[float], closes: list[float], period: int = 9, k_smoothing: int = 3, d_smoothing: int = 3) -> KDJResult:
        length = min(len(highs), len(lows), len(closes))
        series: list[dict[str, float | None]] = [{"k": None, "d": None, "j": None} for _ in range(length)]
        if period < 1 or k_smoothing < 1 or d_smoothing < 1 or length < period:
            return KDJResult(None, None, None, series, True)

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
        return KDJResult(latest["k"], latest["d"], latest["j"], series, False)

    @staticmethod
    def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> IndicatorPoint:
        length = min(len(highs), len(lows), len(closes))
        if period < 1 or length <= period:
            return IndicatorPoint(None, [None for _ in range(length)], True)
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
        return IndicatorPoint(series[-1], series, False)

    @staticmethod
    def obv(closes: list[float], volumes: list[float]) -> IndicatorPoint:
        length = min(len(closes), len(volumes))
        if length == 0:
            return IndicatorPoint(None, [], True)
        series: list[float | None] = [0.0]
        obv_value = 0.0
        for index in range(1, length):
            if closes[index] > closes[index - 1]:
                obv_value += volumes[index]
            elif closes[index] < closes[index - 1]:
                obv_value -= volumes[index]
            series.append(obv_value)
        return IndicatorPoint(series[-1], series, False)

    @staticmethod
    def _rsi_value(average_gain: float, average_loss: float) -> float:
        if average_loss == 0:
            return 100.0 if average_gain > 0 else 50.0
        relative_strength = average_gain / average_loss
        return 100 - (100 / (1 + relative_strength))
