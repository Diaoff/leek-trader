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
    missing_ratio: float = 0.0
    computable: bool = False
    source_fields: tuple[str, ...] = ()


class FactorService:
    def rank_symbols(self, bars_by_symbol: dict[str, list[DailyBarSnapshot]], *, factor: FactorName) -> list[FactorScore]:
        scores = [self._score_symbol(symbol, bars, factor=factor) for symbol, bars in bars_by_symbol.items()]
        ranked_values = sorted((score for score in scores if score.value is not None), key=lambda item: float(item.value), reverse=True)
        ranks = {score.symbol: index + 1 for index, score in enumerate(ranked_values)}
        return [
            FactorScore(
                symbol=score.symbol,
                factor=score.factor,
                value=score.value,
                rank=ranks.get(score.symbol),
                missing_reason=score.missing_reason,
                missing_ratio=score.missing_ratio,
                computable=score.computable,
                source_fields=score.source_fields,
            )
            for score in scores
        ]

    def _score_symbol(self, symbol: str, bars: list[DailyBarSnapshot], *, factor: FactorName) -> FactorScore:
        if not bars:
            return FactorScore(symbol=symbol, factor=factor, value=None, rank=None, missing_reason="no_bars", missing_ratio=1.0, computable=False)
        required_fields = self._source_fields(factor)
        missing_fields = self._missing_fields(bars, required_fields)
        if missing_fields:
            missing_ratio = round(len(missing_fields) / len(required_fields), 6) if required_fields else 0.0
            return FactorScore(
                symbol=symbol,
                factor=factor,
                value=None,
                rank=None,
                missing_reason="missing_fields",
                missing_ratio=missing_ratio,
                computable=False,
                source_fields=required_fields,
            )
        series = IndicatorService.from_bars(bars)
        if factor == "bias":
            result = IndicatorService.bias(series.closes)
            return self._point(symbol, factor, result.bias1, result.insufficient, source_fields=required_fields)
        if factor == "cci":
            result = IndicatorService.cci(series.closes, series.highs, series.lows)
            return self._point(symbol, factor, result.value, result.insufficient, source_fields=required_fields)
        if factor == "bbi":
            result = IndicatorService.bbi(series.closes)
            return self._point(symbol, factor, result.value, result.insufficient, source_fields=required_fields)
        if factor == "wr":
            result = IndicatorService.williams_r(series.closes, series.highs, series.lows)
            return self._point(symbol, factor, result.wr1, result.insufficient, source_fields=required_fields)
        return FactorScore(
            symbol=symbol,
            factor=factor,
            value=None,
            rank=None,
            missing_reason="unsupported_factor",
            missing_ratio=1.0,
            computable=False,
            source_fields=required_fields,
        )

    @staticmethod
    def _point(
        symbol: str,
        factor: FactorName,
        value: float | None,
        insufficient: bool,
        *,
        source_fields: tuple[str, ...],
    ) -> FactorScore:
        return FactorScore(
            symbol=symbol,
            factor=factor,
            value=value,
            rank=None,
            missing_reason="insufficient_history" if insufficient else None,
            missing_ratio=1.0 if insufficient else 0.0,
            computable=(not insufficient and value is not None),
            source_fields=source_fields,
        )

    @staticmethod
    def _source_fields(factor: FactorName) -> tuple[str, ...]:
        if factor in {"cci", "wr"}:
            return ("close_price", "high_price", "low_price")
        return ("close_price",)

    @staticmethod
    def _missing_fields(bars: list[DailyBarSnapshot], required_fields: tuple[str, ...]) -> list[str]:
        missing: list[str] = []
        if not bars:
            return list(required_fields)
        for field_name in required_fields:
            if any(getattr(bar, field_name, None) is None for bar in bars):
                missing.append(field_name)
        return missing
