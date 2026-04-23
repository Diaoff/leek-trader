from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.strategy import StrategyCreate, StrategyRead, StrategyRunRead, StrategyUpdate
from app.strategy.service import StrategyService

router = APIRouter(prefix="/strategies")
service = StrategyService()


@router.get("", response_model=list[StrategyRead])
def list_strategies(db: Session = Depends(get_db)) -> list[StrategyRead]:
    return service.list_strategies(db)


@router.post("", response_model=StrategyRead)
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db)) -> StrategyRead:
    return service.create_strategy(db, payload)


@router.patch("/{strategy_id}", response_model=StrategyRead)
def update_strategy(strategy_id: int, payload: StrategyUpdate, db: Session = Depends(get_db)) -> StrategyRead:
    return service.update_strategy(db, strategy_id, payload)


@router.post("/{strategy_id}/run", response_model=StrategyRunRead)
def run_strategy(strategy_id: int, db: Session = Depends(get_db)) -> StrategyRunRead:
    return service.run_strategy(db, strategy_id)
