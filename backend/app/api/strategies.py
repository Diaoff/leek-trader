from fastapi import APIRouter

from app.schemas.strategy import StrategyRead
from app.strategy.service import StrategyService

router = APIRouter(prefix="/strategies")
service = StrategyService()


@router.get("", response_model=list[StrategyRead])
def list_strategies() -> list[StrategyRead]:
    return service.list_strategies()
