from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.market.data_service import MarketDataService, SOURCE_LABELS
from app.market.history_storage import MarketDailyBarStorage
from app.market.overview_service import MarketOverviewService
from app.market.symbols import normalize_a_share_symbol
from app.schemas.market import DailyBarRead, DailyBarsRead, MarketOverviewRead

router = APIRouter()
overview_service = MarketOverviewService()
market_data_service = MarketDataService()


@router.get("/overview", response_model=MarketOverviewRead)
def get_market_overview() -> MarketOverviewRead:
    return overview_service.get_overview()


@router.get("/daily-bars", response_model=DailyBarsRead)
def get_daily_bars(
    symbol: str = Query(..., min_length=1),
    limit: int = Query(default=60, ge=1, le=5000),
    source: str | None = Query(default=None, pattern="^(baostock)?$"),
    adjustflag: str = Query(default="2"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    fetch_if_missing: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> DailyBarsRead:
    normalized_symbol = normalize_a_share_symbol(symbol)
    if source == "baostock":
        stored = MarketDailyBarStorage(db).list_bars(
            symbol=normalized_symbol,
            source="baostock",
            adjustflag=adjustflag,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            latest=start_date is None and end_date is None,
        )
        if stored.bars or not fetch_if_missing:
            return DailyBarsRead(
                symbol=normalized_symbol,
                source=SOURCE_LABELS["baostock"],
                bars=[daily_bar_to_read(bar) for bar in stored.bars],
            )

    payload = market_data_service.get_daily_bars_with_source(symbol, limit=limit, source=source)
    return DailyBarsRead(
        symbol=normalized_symbol,
        source=SOURCE_LABELS.get(payload.source, payload.source or "none"),
        bars=[daily_bar_to_read(bar) for bar in payload.bars],
    )


def daily_bar_to_read(bar) -> DailyBarRead:
    return DailyBarRead(
        symbol=bar.symbol,
        trade_date=bar.trade_date.isoformat(),
        open_price=bar.open_price,
        close_price=bar.close_price,
        high_price=bar.high_price,
        low_price=bar.low_price,
        volume=bar.volume,
        turnover=bar.turnover,
        amplitude_pct=bar.amplitude_pct,
        change_pct=bar.change_pct,
        turnover_rate=bar.turnover_rate,
        preclose=bar.preclose,
        trade_status=bar.trade_status,
        pe_ttm=bar.pe_ttm,
        pb_mrq=bar.pb_mrq,
        ps_ttm=bar.ps_ttm,
        pcf_ncf_ttm=bar.pcf_ncf_ttm,
        is_st=bar.is_st,
    )
