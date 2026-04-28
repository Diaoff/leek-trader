from dataclasses import dataclass, field
from app.market.data_service import MarketDataService
from app.market.service import QuoteService
from app.schemas.quote import QuoteRead

from .config import DEFAULT_AI_PROMPT_CONFIG


@dataclass(frozen=True)
class AiStockContext:
    quote: QuoteRead | None
    history_csv: str
    history_source: str = "none"
    news_items: list[str] = field(default_factory=list)
    discussion_items: list[str] = field(default_factory=list)


class AiDataLoader:
    def __init__(
        self,
        quote_service: QuoteService | None = None,
        market_data_service: MarketDataService | None = None,
    ) -> None:
        self.market_data_service = market_data_service or MarketDataService(quote_service=quote_service)

    def load_stock_context(self, symbol: str, history_limit: int = DEFAULT_AI_PROMPT_CONFIG.history_limit) -> AiStockContext:
        quote_snapshot = next(iter(self.market_data_service.get_quotes([symbol])), None)
        quote = QuoteService._to_read_model(quote_snapshot) if quote_snapshot is not None else None
        history_csv, history_source = self.fetch_recent_history_csv(symbol, history_limit)
        return AiStockContext(
            quote=quote,
            history_csv=history_csv,
            history_source=history_source,
            news_items=[],
            discussion_items=[],
        )

    def fetch_recent_history_csv(self, symbol: str, limit: int = DEFAULT_AI_PROMPT_CONFIG.history_limit) -> tuple[str, str]:
        return self.market_data_service.get_daily_bars_csv_with_source(symbol, limit=limit)
