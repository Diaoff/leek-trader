from dataclasses import dataclass, field
from sqlalchemy.orm import Session

from app.market.data_service import MarketDataService
from app.market.service import QuoteService
from app.reporting.event_log_service import EventLogService
from app.schemas.quote import QuoteRead

from .config import DEFAULT_AI_PROMPT_CONFIG
from .news_provider import AiNewsProvider


@dataclass(frozen=True)
class AiStockContext:
    quote: QuoteRead | None
    history_csv: str
    history_source: str = "none"
    news_items: list[str] = field(default_factory=list)
    discussion_items: list[str] = field(default_factory=list)
    event_facts: list[dict] = field(default_factory=list)


class AiDataLoader:
    def __init__(
        self,
        quote_service: QuoteService | None = None,
        market_data_service: MarketDataService | None = None,
        news_provider: AiNewsProvider | None = None,
    ) -> None:
        self.market_data_service = market_data_service or MarketDataService(quote_service=quote_service)
        self.news_provider = news_provider or AiNewsProvider()
        self.event_log_service = EventLogService()

    def load_stock_context(
        self,
        symbol: str,
        history_limit: int = DEFAULT_AI_PROMPT_CONFIG.history_limit,
        security_name: str | None = None,
    ) -> AiStockContext:
        quote_snapshot = next(iter(self.market_data_service.get_quotes([symbol])), None)
        quote = QuoteService._to_read_model(quote_snapshot) if quote_snapshot is not None else None
        history_csv, history_source = self.fetch_recent_history_csv(symbol, history_limit)
        keyword = security_name or symbol
        return AiStockContext(
            quote=quote,
            history_csv=history_csv,
            history_source=history_source,
            news_items=self.news_provider.fetch_market_news(),
            discussion_items=self.news_provider.fetch_discussions(keyword),
        )

    def fetch_recent_history_csv(self, symbol: str, limit: int = DEFAULT_AI_PROMPT_CONFIG.history_limit) -> tuple[str, str]:
        return self.market_data_service.get_daily_bars_csv_with_source(symbol, limit=limit)

    def load_event_facts(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        strategy_run_id: int | None = None,
        order_id: int | None = None,
        correlation_id: str | None = None,
    ) -> list[dict]:
        return self.event_log_service.facts_for_context(
            db,
            user_id=user_id,
            strategy_run_id=strategy_run_id,
            order_id=order_id,
            correlation_id=correlation_id,
        )
