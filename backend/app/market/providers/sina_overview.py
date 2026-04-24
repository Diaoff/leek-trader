from __future__ import annotations

from datetime import UTC, datetime

from app.market.providers.base import MarketOverviewProvider, MarketOverviewSnapshot, MarketSymbolSnapshot
from app.market.providers.sina import SinaQuoteProvider


class SinaOverviewProvider(MarketOverviewProvider):
    name = "sina"
    index_symbols: list[tuple[str, str]] = [
        ("上证指数", "sh000001"),
        ("深证成指", "sz399001"),
        ("创业板指", "sz399006"),
    ]

    def __init__(self, quote_provider: SinaQuoteProvider | None = None) -> None:
        self.quote_provider = quote_provider or SinaQuoteProvider()

    def fetch_overview(self) -> MarketOverviewSnapshot:
        quotes = self.quote_provider.fetch_quotes([symbol for _, symbol in self.index_symbols])
        by_symbol = {quote.symbol: quote for quote in quotes}

        indices = [
            MarketSymbolSnapshot(
                symbol=symbol,
                code=symbol[2:],
                name=name,
                price=by_symbol.get(symbol).price if by_symbol.get(symbol) else None,
                change_percent=by_symbol.get(symbol).change_percent if by_symbol.get(symbol) else None,
                volume=by_symbol.get(symbol).volume if by_symbol.get(symbol) else 0.0,
            )
            for name, symbol in self.index_symbols
        ]

        generated_at = max((quote.timestamp for quote in quotes), default=datetime.now(UTC))
        return MarketOverviewSnapshot(
            generated_at=generated_at,
            source=self.name,
            indices=indices,
            northbound_net_inflow=None,
        )
