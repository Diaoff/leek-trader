from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.backtest.jobs import BacktestJobRegistry
from app.backtest.service import BacktestService
from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.backtest import BacktestDailyReviewRead, BacktestDailyReviewRequest, BacktestJobRead, BacktestRunRead, BacktestRunRequest

router = APIRouter(prefix="/backtest")
service = BacktestService()
job_registry = BacktestJobRegistry()


@router.post("/jobs", response_model=BacktestJobRead)
def submit_backtest_job(
    payload: BacktestRunRequest,
    current_user: User = Depends(get_current_active_user),
) -> BacktestJobRead:
    job_payload = payload.model_dump(mode="json")
    job_payload["tenant_id"] = settings.default_tenant_id
    job_payload["user_id"] = current_user.id
    job = job_registry.submit(job_payload)
    return BacktestJobRead(**job)


@router.get("/jobs/latest", response_model=BacktestJobRead)
def get_latest_backtest_job(current_user: User = Depends(get_current_active_user)) -> BacktestJobRead:
    job = job_registry.latest(current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="backtest job not found")
    return BacktestJobRead(**job)


@router.get("/jobs/{job_id}", response_model=BacktestJobRead)
def get_backtest_job(job_id: str, current_user: User = Depends(get_current_active_user)) -> BacktestJobRead:
    job = job_registry.get(job_id)
    if job is None or int((job.get("payload") or {}).get("user_id") or 0) != current_user.id:
        raise HTTPException(status_code=404, detail="backtest job not found")
    return BacktestJobRead(**job)


@router.post("/run", response_model=BacktestRunRead)
def run_backtest(
    payload: BacktestRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BacktestRunRead:
    result = service.run_single_symbol_backtest(db, tenant_id=settings.default_tenant_id, user_id=current_user.id, **payload.model_dump())
    return BacktestRunRead(**result)


@router.post("/daily-review", response_model=BacktestDailyReviewRead)
def build_daily_review(
    payload: BacktestDailyReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BacktestDailyReviewRead:
    result = service.build_daily_review(db, tenant_id=settings.default_tenant_id, user_id=current_user.id, **payload.model_dump())
    return BacktestDailyReviewRead(**result)
