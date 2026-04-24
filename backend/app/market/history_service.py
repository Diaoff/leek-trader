from __future__ import annotations

import logging

from app.market.providers.base import DailyBarSnapshot, PriceHistoryProvider
from app.market.providers.eastmoney import EastMoneyQuoteProvider

logger = logging.getLogger(__name__)


class HistoryService:
    def __init__(self, providers: list[PriceHistoryProvider] | None = None) -> None:
        self.providers = providers or [EastMoneyQuoteProvider()]

    def get_daily_bars(self, symbol: str, limit: int = 60) -> list[DailyBarSnapshot]:
        for provider in self.providers:
            try:
                bars = provider.fetch_daily_bars(symbol, limit=limit)
            except Exception as error:
                logger.warning("History provider %s failed for symbol=%s: %s", provider.name, symbol, error)
                continue
            if bars:
                return bars
        return []

    def get_daily_bars_map(self, symbols: list[str], limit: int = 60) -> dict[str, list[DailyBarSnapshot]]:
        result: dict[str, list[DailyBarSnapshot]] = {}
        for symbol in symbols:
            result[symbol] = self.get_daily_bars(symbol, limit=limit)
        return result
