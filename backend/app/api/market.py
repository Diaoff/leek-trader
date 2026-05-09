from __future__ import annotations

from fastapi import APIRouter

from app.api.market_routes.baostock import BaoStockHistorySyncService, router as baostock_router, sync_baostock_history_task
from app.api.market_routes.overview import market_data_service, router as overview_router
from app.api.market_routes.rl import router as rl_router

router = APIRouter(prefix="/market")
router.include_router(overview_router)
router.include_router(baostock_router)
router.include_router(rl_router)

__all__ = [
    "BaoStockHistorySyncService",
    "market_data_service",
    "router",
    "sync_baostock_history_task",
]
