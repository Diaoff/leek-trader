from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.audit import audit_event
from app.core.db import get_db
from app.devtools.reset_service import DevResetService
from app.models.user import User
from app.schemas.devtools import SystemBenchmarkRead, TradingStateResetRead, TradingStateResetRequest

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
        audit_event(
            "devtools.reset_trading_state",
            actor_id=current_user.id,
            actor_name=current_user.username,
            tenant_id=current_user.tenant_id,
            resource_type="trading_state",
            outcome="rejected",
            details={"reason": str(error)},
        )
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit_event(
        "devtools.reset_trading_state",
        actor_id=current_user.id,
        actor_name=current_user.username,
        tenant_id=current_user.tenant_id,
        resource_type="trading_state",
        outcome="success",
        details={"deleted_counts": result.get("deleted_counts", {}), "initial_cash": result.get("initial_cash")},
    )
    return TradingStateResetRead(**result)


@router.get("/system-benchmark", response_model=SystemBenchmarkRead)
def system_benchmark(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SystemBenchmarkRead:
    result = service.benchmark_system(db, user_id=current_user.id)
    return SystemBenchmarkRead(**result)
