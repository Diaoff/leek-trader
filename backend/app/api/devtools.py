from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.devtools.reset_service import DevResetService
from app.schemas.devtools import TradingStateResetRead, TradingStateResetRequest

router = APIRouter(prefix="/devtools")
service = DevResetService()


@router.post("/reset-trading-state", response_model=TradingStateResetRead)
def reset_trading_state(payload: TradingStateResetRequest, db: Session = Depends(get_db)) -> TradingStateResetRead:
    try:
        result = service.reset_trading_state(
            db,
            confirmation=payload.confirmation,
            initial_cash=payload.initial_cash,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return TradingStateResetRead(**result)
