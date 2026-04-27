from __future__ import annotations

from fastapi import APIRouter

from app.market.overview_service import MarketOverviewService
from app.schemas.market import MarketOverviewRead

router = APIRouter(prefix="/market")
overview_service = MarketOverviewService()


@router.get("/overview", response_model=MarketOverviewRead)
def get_market_overview() -> MarketOverviewRead:
    return overview_service.get_overview()
