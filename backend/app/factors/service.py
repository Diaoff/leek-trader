from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.indicators.service import IndicatorService
from app.market.providers.base import DailyBarSnapshot

FactorName = Literal["bias", "cci", "bbi", "wr"]


@dataclass(frozen=True, slots=True)
class FactorScore:
    symbol: str
    factor: FactorName
    value: float | None
    rank: int | None
    missing_reason: str | None = None


class FactorService:
    def rank_symbols(self, bars_by_symbol: dict[str, list[DailyBarSnapshot]], *, factor: FactorName) -> list[FactorScore]:
        scores = [self._score_symbol(symbol, bars, factor=factor) for symbol, bars in bars_by_symbol.items()]
        ranked_values = sorted((score for score in scores if score.value is not None), key=lambda item: float(item.value), reverse=True)
        ranks = {score.symbol: index + 1 for index, score in enumerate(ranked_values)}
        return [
            FactorScore(symbol=score.symbol, factor=score.factor, value=score.value, rank=ranks.get(score.symbol), missing_reason=score.missing_reason)
            for score in scores
        ]

    def _score_symbol(self, symbol: str, bars: list[DailyBarSnapshot], *, factor: FactorName) -> FactorScore:
        if not bars:
            return FactorScore(symbol=symbol, factor=factor, value=None, rank=None, missing_reason="no_bars")
        series = IndicatorService.from_bars(bars)
        if factor == "bias":
            result = IndicatorService.bias(series.closes)
            return self._point(symbol, factor, result.bias1, result.insufficient)
        if factor == "cci":
            result = IndicatorService.cci(series.closes, series.highs, series.lows)
            return self._point(symbol, factor, result.value, result.insufficient)
        if factor == "bbi":
            result = IndicatorService.bbi(series.closes)
            return self._point(symbol, factor, result.value, result.insufficient)
        if factor == "wr":
            result = IndicatorService.williams_r(series.closes, series.highs, series.lows)
            return self._point(symbol, factor, result.wr1, result.insufficient)
        return FactorScore(symbol=symbol, factor=factor, value=None, rank=None, missing_reason="unsupported_factor")

    @staticmethod
    def _point(symbol: str, factor: FactorName, value: float | None, insufficient: bool) -> FactorScore:
        return FactorScore(symbol=symbol, factor=factor, value=value, rank=None, missing_reason="insufficient_history" if insufficient else None)
