from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.db import get_db
from app.models.user import User
from app.portfolio.service import PortfolioService
from app.schemas.portfolio import PortfolioSummary
from app.trading.service import TradingService

router = APIRouter(prefix="/portfolio")
service = PortfolioService()
trading_service = TradingService()


@router.get("/summary", response_model=PortfolioSummary)
def get_portfolio_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PortfolioSummary:
    trading_service.match_pending_orders(db, current_user.id)
    return PortfolioSummary(**service.get_summary(db, current_user.id))
