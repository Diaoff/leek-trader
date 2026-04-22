from app.market.providers.base import QuoteProvider, QuoteSnapshot


class AkshareQuoteProvider(QuoteProvider):
    name = "akshare"

    def fetch_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        return self.build_placeholder_quotes(symbols)
