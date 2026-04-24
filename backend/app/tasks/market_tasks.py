import logging

from app.core.config import settings
from app.core.celery_app import celery_app
from app.market.service import QuoteService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.market_tasks.refresh_market_quotes_task", bind=True)
def refresh_market_quotes_task(self, symbols: list[str] | None = None) -> dict[str, object]:
    target_symbols = symbols or settings.market_refresh_symbol_list
    logger.info(
        "Celery task started task=%s task_id=%s symbols=%s",
        self.name,
        self.request.id,
        target_symbols,
    )
    quotes = QuoteService().refresh_quotes(target_symbols)
    result = {
        "status": "refreshed",
        "task": "refresh_market_quotes",
        "symbols": target_symbols,
        "count": len(quotes),
    }
    logger.info(
        "Celery task succeeded task=%s task_id=%s count=%s",
        self.name,
        self.request.id,
        result["count"],
    )
    return result


def refresh_market_quotes() -> dict[str, object]:
    return refresh_market_quotes_task(settings.market_refresh_symbol_list)
