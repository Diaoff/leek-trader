import logging

from app.market.providers.akshare_provider import AkshareQuoteProvider
from app.market.providers.base import QuoteProvider, QuoteSnapshot
from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.providers.sina import SinaQuoteProvider
from app.schemas.quote import QuoteRead

logger = logging.getLogger(__name__)


class QuoteService:
    def __init__(self, providers: list[QuoteProvider] | None = None) -> None:
        self.providers = providers or [
            SinaQuoteProvider(),
            EastMoneyQuoteProvider(),
            AkshareQuoteProvider(),
        ]

    def list_quotes(self, symbols: list[str]) -> list[QuoteRead]:
        snapshots = self._fetch_with_fallback(symbols or ["sh600519", "sz000001"])
        return [
            QuoteRead(
                symbol=item.symbol,
                price=item.price,
                change_percent=item.change_percent,
                volume=item.volume,
                timestamp=item.timestamp.isoformat(),
                is_halted=item.is_halted,
            )
            for item in snapshots
        ]

    def _fetch_with_fallback(self, symbols: list[str]) -> list[QuoteSnapshot]:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                snapshots = provider.fetch_quotes(symbols)
            except Exception as error:
                logger.warning("Quote provider %s failed: %s", provider.name, error)
                last_error = error
                continue
            if snapshots:
                return snapshots
        if last_error is not None:
            raise last_error
        return []
