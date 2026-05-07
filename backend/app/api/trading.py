from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.db import get_db
from app.models.user import User
from app.trading.service import TradingService

router = APIRouter(prefix="/trading")
service = TradingService()


@router.post("/simulate")
def simulate_trade(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, object]:
    try:
        symbol = service.resolve_simulation_symbol(db, current_user.id)
    except TypeError:
        symbol = service.resolve_simulation_symbol(db)
    if not symbol:
        raise HTTPException(status_code=400, detail="no symbol available for simulation")
    return service.simulate_execution(db, symbol=symbol, user_id=current_user.id)
