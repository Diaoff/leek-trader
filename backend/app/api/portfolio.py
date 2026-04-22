from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.portfolio.service import PortfolioService
from app.schemas.portfolio import PortfolioSummary
from app.trading.service import TradingService

router = APIRouter(prefix="/portfolio")
service = PortfolioService()
trading_service = TradingService()


@router.get("/summary", response_model=PortfolioSummary)
def get_portfolio_summary(db: Session = Depends(get_db)) -> PortfolioSummary:
    trading_service.match_pending_orders(db)
    return PortfolioSummary(**service.get_summary(db))
