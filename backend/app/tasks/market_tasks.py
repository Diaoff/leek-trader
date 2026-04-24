import logging

from app.core.config import settings
from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.market.research_service import MarketResearchService
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


@celery_app.task(name="app.tasks.market_tasks.run_market_research_task", bind=True)
def run_market_research_task(
    self,
    run_id: int | None = None,
    triggered_by: str = "system",
) -> dict[str, object]:
    service = MarketResearchService()
    logger.info(
        "Celery task started task=%s task_id=%s run_id=%s triggered_by=%s",
        self.name,
        self.request.id,
        run_id,
        triggered_by,
    )
    with SessionLocal() as db:
        run = service.execute_run(db, run_id=run_id, task_id=self.request.id, triggered_by=triggered_by)

    result = {
        "status": "completed",
        "task": "run_market_research",
        "run_id": run.id,
        "task_id": self.request.id,
        "recommendation_count": run.recommendation_count,
    }
    logger.info(
        "Celery task succeeded task=%s task_id=%s run_id=%s count=%s",
        self.name,
        self.request.id,
        run.id,
        run.recommendation_count,
    )
    return result
