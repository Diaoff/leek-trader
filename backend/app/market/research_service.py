from __future__ import annotations

from dataclasses import dataclass

from app.market.providers.adata_research import ADataResearchProvider
from app.market.providers.base import DragonTigerStockSnapshot, ResearchProvider, StockFundFlowSnapshot
from app.market.symbols import normalize_a_share_symbol


@dataclass(slots=True)
class DragonTigerQueryResult:
    items: list[DragonTigerStockSnapshot]
    source: str


class MarketResearchService:
    def __init__(self, provider: ResearchProvider | None = None) -> None:
        self.provider = provider or ADataResearchProvider()

    def get_stock_fund_flow(self, symbol: str) -> StockFundFlowSnapshot:
        normalized = normalize_a_share_symbol(symbol)
        return self.provider.fetch_stock_fund_flow(normalized or symbol)

    def get_dragon_tiger(self, *, trade_date: str | None = None, symbol: str | None = None) -> DragonTigerQueryResult:
        normalized = normalize_a_share_symbol(symbol) if symbol else None
        items = self.provider.fetch_dragon_tiger(trade_date=trade_date, symbol=normalized)
        return DragonTigerQueryResult(items=items, source=self.provider.name)
