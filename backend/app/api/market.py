from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from kombu.exceptions import OperationalError as KombuOperationalError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.market.overview_service import MarketOverviewService
from app.market.research_service import MarketResearchService
from app.schemas.market import (
    MarketOverviewRead,
    MarketRecommendationRead,
    MarketResearchHistoryRead,
    MarketResearchLatestRead,
    MarketResearchRunDispatchRead,
)
from app.tasks.market_tasks import run_market_research_task

router = APIRouter(prefix="/market")
overview_service = MarketOverviewService()
research_service = MarketResearchService(overview_service=overview_service)


def _is_broker_unavailable_error(error: Exception) -> bool:
    if isinstance(error, (KombuOperationalError, OSError, TimeoutError)):
        return True

    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "connection refused",
            "connection is bad",
            "redis",
            "broker",
            "temporarily unavailable",
            "operation not permitted",
        )
    )


@router.get("/overview", response_model=MarketOverviewRead)
def get_market_overview(db: Session = Depends(get_db)) -> MarketOverviewRead:
    overview = overview_service.get_overview()
    return research_service.augment_overview(overview, db)


@router.get("/recommendations", response_model=list[MarketRecommendationRead])
def get_market_recommendations(db: Session = Depends(get_db)) -> list[MarketRecommendationRead]:
    return research_service.list_latest_recommendations(db)


@router.get("/research/latest", response_model=MarketResearchLatestRead)
def get_latest_market_research(db: Session = Depends(get_db)) -> MarketResearchLatestRead:
    return research_service.get_latest_snapshot(db)


@router.get("/research/history", response_model=MarketResearchHistoryRead)
def get_market_research_history(limit: int = 10, db: Session = Depends(get_db)) -> MarketResearchHistoryRead:
    safe_limit = min(max(limit, 1), 30)
    return MarketResearchHistoryRead(runs=research_service.list_history(db, limit=safe_limit))


@router.post("/research/run", response_model=MarketResearchRunDispatchRead)
def trigger_market_research(db: Session = Depends(get_db)) -> MarketResearchRunDispatchRead:
    run = research_service.create_run(db, triggered_by="manual")
    try:
        result = run_market_research_task.apply_async(kwargs={"run_id": run.id, "triggered_by": "manual"})
    except Exception as error:
        research_service.fail_run(db, run.id, error_message=str(error))
        if _is_broker_unavailable_error(error):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="消息队列不可用，请检查 Redis / Celery broker 后重试",
            ) from error
        raise

    research_service.mark_run_queued(db, run.id, task_id=result.id)
    return MarketResearchRunDispatchRead(status="queued", run_id=run.id, task_id=result.id)
