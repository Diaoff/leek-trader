from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.db import get_db
from app.market.security_catalog import screen_securities, search_securities
from app.market.service import QuoteService
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.schemas.quote import QuoteRead
from app.schemas.security import SecurityScreenResult, SecuritySearchResult

router = APIRouter(prefix="/securities")
quote_service = QuoteService()


@router.get("/search", response_model=list[SecuritySearchResult])
def search_security(q: str = Query(min_length=1)) -> list[SecuritySearchResult]:
    return [SecuritySearchResult(**item) for item in search_securities(q)]


@router.get("/screen", response_model=list[SecurityScreenResult])
def screen_security_pool(
    market: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    exclude_st: bool = True,
    tags: list[str] = Query(default=[]),
    min_market_cap: float | None = Query(default=None, ge=0),
    max_market_cap: float | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[SecurityScreenResult]:
    fetch_limit = limit
    market_cap_filter_requested = min_market_cap is not None or max_market_cap is not None
    if market_cap_filter_requested:
        fetch_limit = min(max(limit * 5, limit), 200)
    entries = screen_securities(market=market, query=q, exclude_st=exclude_st, tags=tags, limit=fetch_limit)
    symbols = [str(item["symbol"]) for item in entries]
    quote_map = _load_quote_map(symbols) if market_cap_filter_requested else {}
    if market_cap_filter_requested:
        entries = [
            item for item in entries
            if _matches_market_cap(quote_map.get(str(item["symbol"])), min_market_cap, max_market_cap)
        ]
        entries = entries[:limit]
        symbols = [str(item["symbol"]) for item in entries]

    watchlist_symbols = set(
        db.scalars(
            select(WatchlistItem.symbol).where(
                WatchlistItem.tenant_id == settings.default_tenant_id,
                WatchlistItem.user_id == current_user.id,
                WatchlistItem.symbol.in_(symbols),
            )
        ).all()
    ) if symbols else set()

    return [
        SecurityScreenResult(
            **item,
            in_watchlist=str(item["symbol"]) in watchlist_symbols,
            market_cap=quote_map[str(item["symbol"])].market_cap if str(item["symbol"]) in quote_map else None,
            price=quote_map[str(item["symbol"])].price if str(item["symbol"]) in quote_map else None,
            change_percent=quote_map[str(item["symbol"])].change_percent if str(item["symbol"]) in quote_map else None,
        )
        for item in entries
    ]


def _load_quote_map(symbols: list[str]) -> dict[str, QuoteRead]:
    if not symbols:
        return {}
    return {quote.symbol: quote for quote in quote_service.list_quotes(symbols)}


def _matches_market_cap(quote: QuoteRead | None, min_market_cap: float | None, max_market_cap: float | None) -> bool:
    market_cap = quote.market_cap if quote is not None else None
    if market_cap is None:
        return False
    if min_market_cap is not None and market_cap < min_market_cap:
        return False
    if max_market_cap is not None and market_cap > max_market_cap:
        return False
    return True
