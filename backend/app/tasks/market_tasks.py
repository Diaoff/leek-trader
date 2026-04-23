from app.core.config import settings
from app.core.celery_app import celery_app
from app.market.service import QuoteService


@celery_app.task(name="app.tasks.market_tasks.refresh_market_quotes_task")
def refresh_market_quotes_task(symbols: list[str] | None = None) -> dict[str, object]:
    target_symbols = symbols or settings.market_refresh_symbol_list
    quotes = QuoteService().refresh_quotes(target_symbols)
    return {
        "status": "refreshed",
        "task": "refresh_market_quotes",
        "symbols": target_symbols,
        "count": len(quotes),
    }


def refresh_market_quotes() -> dict[str, object]:
    return refresh_market_quotes_task(settings.market_refresh_symbol_list)
