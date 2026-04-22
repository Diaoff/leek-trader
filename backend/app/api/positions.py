from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.account import Account
from app.models.position import Position
from app.portfolio.service import PortfolioService
from app.schemas.position import PositionRead
from app.trading.service import TradingService

router = APIRouter(prefix="/positions")
service = PortfolioService()
trading_service = TradingService()


@router.get("", response_model=list[PositionRead])
def list_positions(db: Session = Depends(get_db)) -> list[PositionRead]:
    account = db.scalar(
        select(Account).where(
            Account.tenant_id == settings.default_tenant_id,
            Account.name == settings.default_account_name,
        )
    )
    if account is None:
        return []

    trading_service.match_pending_orders(db)
    service.refresh_positions_with_quotes(db, account.id)
    positions = db.scalars(
        select(Position)
        .where(Position.account_id == account.id, Position.quantity > 0)
        .order_by(Position.symbol)
    ).all()
    return [PositionRead.model_validate(position) for position in positions]
