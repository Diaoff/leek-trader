from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.trading.service import TradingService

router = APIRouter(prefix="/trading")
service = TradingService()


@router.post("/simulate")
def simulate_trade(db: Session = Depends(get_db)) -> dict[str, object]:
    symbol = service.resolve_simulation_symbol(db)
    if not symbol:
        raise HTTPException(status_code=400, detail="no symbol available for simulation")
    return service.simulate_execution(db, symbol=symbol)
