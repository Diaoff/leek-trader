from __future__ import annotations

from app.core.config import settings
from app.market.providers.base import DailyBarSnapshot, PriceHistoryProvider
from app.market.data_service import DailyBarCache, MarketDataService


class HistoryService:
    def __init__(
        self,
        providers: list[PriceHistoryProvider] | None = None,
        cache: DailyBarCache | None = None,
    ) -> None:
        if providers is not None and cache is None:
            cache = DailyBarCache(ttl_seconds=settings.market_history_cache_ttl_seconds, redis_url=None)
        self.market_data = MarketDataService(history_providers=providers, history_cache=cache)

    @property
    def providers(self) -> list[PriceHistoryProvider]:
        return self.market_data.providers

    @providers.setter
    def providers(self, providers: list[PriceHistoryProvider]) -> None:
        self.market_data.providers = providers

    def get_daily_bars(self, symbol: str, limit: int = 60, *, source: str | None = None) -> list[DailyBarSnapshot]:
        return self.market_data.get_daily_bars(symbol, limit=limit, source=source)

    def get_daily_bars_map(
        self,
        symbols: list[str],
        limit: int = 60,
        *,
        source: str | None = None,
    ) -> dict[str, list[DailyBarSnapshot]]:
        result: dict[str, list[DailyBarSnapshot]] = {}
        for symbol in symbols:
            result[symbol] = self.get_daily_bars(symbol, limit=limit, source=source)
        return result
