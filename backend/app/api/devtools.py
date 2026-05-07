from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.db import get_db
from app.devtools.reset_service import DevResetService
from app.models.user import User
from app.schemas.devtools import TradingStateResetRead, TradingStateResetRequest

router = APIRouter(prefix="/devtools")
service = DevResetService()


@router.post("/reset-trading-state", response_model=TradingStateResetRead)
def reset_trading_state(
    payload: TradingStateResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TradingStateResetRead:
    try:
        result = service.reset_trading_state(
            db,
            confirmation=payload.confirmation,
            initial_cash=payload.initial_cash,
            user_id=current_user.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return TradingStateResetRead(**result)
