from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.strategy import StrategyCreate, StrategyDeleteRead, StrategyRead, StrategyRunHistoryRead, StrategyRunRead, StrategyUpdate
from app.strategy.service import StrategyService

router = APIRouter(prefix="/strategies")
service = StrategyService()


@router.get("", response_model=list[StrategyRead])
def list_strategies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[StrategyRead]:
    return service.list_strategies(db, settings.default_tenant_id, current_user.id)


@router.get("/runs/latest", response_model=StrategyRunRead | None)
def get_latest_strategy_run(
    strategy_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StrategyRunRead | None:
    return service.get_latest_run(db, strategy_id=strategy_id, user_id=current_user.id)


@router.get("/runs/history", response_model=StrategyRunHistoryRead)
def get_strategy_run_history(
    limit: int = 10,
    strategy_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StrategyRunHistoryRead:
    safe_limit = max(1, min(limit, 20))
    return StrategyRunHistoryRead(runs=service.list_run_history(db, limit=safe_limit, strategy_id=strategy_id, user_id=current_user.id))


@router.post("", response_model=StrategyRead)
def create_strategy(
    payload: StrategyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StrategyRead:
    return service.create_strategy(db, payload, settings.default_tenant_id, current_user.id)


@router.patch("/{strategy_id}", response_model=StrategyRead)
def update_strategy(
    strategy_id: int,
    payload: StrategyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StrategyRead:
    return service.update_strategy(db, strategy_id, payload, settings.default_tenant_id, current_user.id)


@router.delete("/{strategy_id}", response_model=StrategyDeleteRead)
def delete_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StrategyDeleteRead:
    return service.delete_strategy(db, strategy_id, settings.default_tenant_id, current_user.id)


@router.post("/{strategy_id}/run", response_model=StrategyRunRead)
def run_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StrategyRunRead:
    return service.run_strategy(db, strategy_id, settings.default_tenant_id, current_user.id)
