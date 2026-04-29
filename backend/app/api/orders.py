from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.order import Order
from app.market.security_names import security_name
from app.schemas.order import OrderCreate, OrderRead
from app.trading.service import TradingService

router = APIRouter(prefix="/orders")
service = TradingService()


@router.get("", response_model=list[OrderRead])
def list_orders(db: Session = Depends(get_db)) -> list[OrderRead]:
    service.match_pending_orders(db)
    orders = db.scalars(select(Order).order_by(Order.created_at.desc(), Order.id.desc())).all()
    return [
        OrderRead.model_validate(order).model_copy(update={"name": security_name(order.symbol)})
        for order in orders
    ]


@router.post("")
def create_order(payload: OrderCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    return service.place_order(
        db,
        symbol=payload.symbol,
        side=payload.side,
        order_type=payload.order_type,
        quantity=payload.quantity,
        price=float(payload.price),
    )


@router.post("/{order_id}/cancel")
def cancel_order(order_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return service.cancel_order(db, order_id)


@router.post("/match-pending")
def match_pending_orders(db: Session = Depends(get_db)) -> dict[str, object]:
    return service.match_pending_orders(db)
