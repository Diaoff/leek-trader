from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.trading.service import TradingService

router = APIRouter(prefix="/trading")
service = TradingService()


@router.post("/simulate")
def simulate_trade(db: Session = Depends(get_db)) -> dict[str, object]:
    return service.simulate_execution(db)
