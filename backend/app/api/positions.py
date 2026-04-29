from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.account import Account
from app.models.position import Position
from app.market.security_names import security_name
from app.portfolio.service import PortfolioService
from app.schemas.position import PositionExitGuardUpdate, PositionRead
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

    trading_service.unlock_settled_positions(db, account.id)
    trading_service.match_pending_orders(db)
    service.refresh_positions_with_quotes(db, account.id)
    positions = db.scalars(
        select(Position)
        .where(Position.account_id == account.id, Position.quantity > 0)
        .order_by(Position.symbol)
    ).all()
    return [
        PositionRead.model_validate(position).model_copy(update={"name": security_name(position.symbol)})
        for position in positions
    ]


@router.patch("/{position_id}/exit-guard", response_model=PositionRead)
def update_position_exit_guard(
    position_id: int,
    payload: PositionExitGuardUpdate,
    db: Session = Depends(get_db),
) -> PositionRead:
    position = trading_service.update_position_exit_guard(
        db,
        position_id=position_id,
        stop_loss_price=float(payload.stop_loss_price) if payload.stop_loss_price is not None else None,
        take_profit_price=float(payload.take_profit_price) if payload.take_profit_price is not None else None,
    )
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")
    return PositionRead.model_validate(position).model_copy(update={"name": security_name(position.symbol)})
