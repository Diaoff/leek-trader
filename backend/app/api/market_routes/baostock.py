from __future__ import annotations

from datetime import date
from importlib import import_module

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.market_routes.overview import daily_bar_to_read
from app.core.auth import get_current_superuser
from app.core.db import get_db
from app.market.baostock_sync_service import BaoStockHistorySyncService
from app.market.data_service import SOURCE_LABELS
from app.market.history_storage import MarketDailyBarStorage
from app.market.symbols import normalize_a_share_symbol
from app.models.user import User
from app.schemas.market import BaoStockHistorySyncRequest, BaoStockHistorySyncResultRead, BaoStockHistorySyncTaskRead, DailyBarsRead
from app.tasks.market_tasks import sync_baostock_history_task

router = APIRouter()


@router.post("/baostock/history/sync", response_model=BaoStockHistorySyncTaskRead)
def submit_baostock_history_sync(
    payload: BaoStockHistorySyncRequest,
    current_user: User = Depends(get_current_superuser),
) -> BaoStockHistorySyncTaskRead:
    if not payload.symbols:
        raise HTTPException(status_code=422, detail="symbols must be a non-empty explicit list")
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=422, detail="start_date must be before or equal to end_date")
    task = _compat_market_api().sync_baostock_history_task.delay(
        payload.symbols,
        payload.start_date.isoformat(),
        payload.end_date.isoformat(),
        payload.adjustflag,
        payload.incremental,
    )
    return BaoStockHistorySyncTaskRead(task_id=task.id, status="submitted")


@router.post("/baostock/history/sync-now", response_model=BaoStockHistorySyncResultRead)
def run_baostock_history_sync_now(
    payload: BaoStockHistorySyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> BaoStockHistorySyncResultRead:
    try:
        result = _compat_market_api().BaoStockHistorySyncService(db).sync_history(
            symbols=payload.symbols,
            start_date=payload.start_date,
            end_date=payload.end_date,
            adjustflag=payload.adjustflag,
            incremental=payload.incremental,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return BaoStockHistorySyncResultRead(**result.to_dict())


@router.get("/baostock/history", response_model=DailyBarsRead)
def read_baostock_history(
    symbol: str = Query(..., min_length=1),
    adjustflag: str = Query(default="2"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=50000),
    db: Session = Depends(get_db),
) -> DailyBarsRead:
    result = MarketDailyBarStorage(db).list_bars(
        symbol=symbol,
        source="baostock",
        adjustflag=adjustflag,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return DailyBarsRead(
        symbol=result.symbol or normalize_a_share_symbol(symbol),
        source=SOURCE_LABELS["baostock"],
        bars=[daily_bar_to_read(bar) for bar in result.bars],
    )


def _compat_market_api():
    return import_module("app.api.market")
