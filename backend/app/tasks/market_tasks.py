import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.market.service import QuoteService
from app.models.position import Position
from app.models.strategy import Strategy, StrategyStatus
from app.models.watchlist import WatchlistItem

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.market_tasks.refresh_market_quotes_task", bind=True)
def refresh_market_quotes_task(self, symbols: list[str] | None = None) -> dict[str, object]:
    if symbols is None:
        with SessionLocal() as db:
            target_symbols = _resolve_refresh_symbols(db)
    else:
        target_symbols = _normalize_symbols(symbols)
    logger.info(
        "Celery task started task=%s task_id=%s symbols=%s",
        self.name,
        self.request.id,
        target_symbols,
    )
    if not target_symbols:
        result = {
            "status": "skipped",
            "task": "refresh_market_quotes",
            "symbols": [],
            "count": 0,
        }
        logger.info(
            "Celery task skipped task=%s task_id=%s reason=no_symbols",
            self.name,
            self.request.id,
        )
        return result
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
    return refresh_market_quotes_task()


def _resolve_refresh_symbols(db) -> list[str]:
    candidates: list[str] = []
    candidates.extend(settings.market_refresh_symbol_list)
    candidates.extend(
        db.scalars(
            select(WatchlistItem.symbol)
            .where(WatchlistItem.tenant_id == settings.default_tenant_id)
            .order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
        ).all()
    )
    candidates.extend(
        db.scalars(
            select(Position.symbol)
            .where(Position.tenant_id == settings.default_tenant_id)
            .order_by(Position.updated_at.desc(), Position.id.desc())
        ).all()
    )
    candidates.extend(
        db.scalars(
            select(Strategy.symbol)
            .where(
                Strategy.tenant_id == settings.default_tenant_id,
                Strategy.status == StrategyStatus.ACTIVE,
            )
            .order_by(Strategy.updated_at.desc(), Strategy.id.desc())
        ).all()
    )
    return _normalize_symbols(candidates)


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol or normalized_symbol in seen:
            continue
        seen.add(normalized_symbol)
        normalized.append(normalized_symbol)
    return normalized
