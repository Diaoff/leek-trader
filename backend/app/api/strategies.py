from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.strategy import StrategyCreate, StrategyRead, StrategyRunHistoryRead, StrategyRunRead, StrategyUpdate
from app.strategy.service import StrategyService

router = APIRouter(prefix="/strategies")
service = StrategyService()


@router.get("", response_model=list[StrategyRead])
def list_strategies(db: Session = Depends(get_db)) -> list[StrategyRead]:
    return service.list_strategies(db)


@router.get("/runs/latest", response_model=StrategyRunRead | None)
def get_latest_strategy_run(strategy_id: int | None = None, db: Session = Depends(get_db)) -> StrategyRunRead | None:
    return service.get_latest_run(db, strategy_id=strategy_id)


@router.get("/runs/history", response_model=StrategyRunHistoryRead)
def get_strategy_run_history(
    limit: int = 10,
    strategy_id: int | None = None,
    db: Session = Depends(get_db),
) -> StrategyRunHistoryRead:
    safe_limit = max(1, min(limit, 20))
    return StrategyRunHistoryRead(runs=service.list_run_history(db, limit=safe_limit, strategy_id=strategy_id))


@router.post("", response_model=StrategyRead)
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db)) -> StrategyRead:
    return service.create_strategy(db, payload)


@router.patch("/{strategy_id}", response_model=StrategyRead)
def update_strategy(strategy_id: int, payload: StrategyUpdate, db: Session = Depends(get_db)) -> StrategyRead:
    return service.update_strategy(db, strategy_id, payload)


@router.post("/{strategy_id}/run", response_model=StrategyRunRead)
def run_strategy(strategy_id: int, db: Session = Depends(get_db)) -> StrategyRunRead:
    return service.run_strategy(db, strategy_id)
