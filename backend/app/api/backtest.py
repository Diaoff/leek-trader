from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.backtest.jobs import BacktestJobRegistry
from app.backtest.service import BacktestService
from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.backtest import (
    BacktestDailyReviewRead,
    BacktestDailyReviewRequest,
    BacktestJobRead,
    BacktestOptimizationHistoryRead,
    BacktestOptimizationJobRead,
    BacktestOptimizationRequest,
    BacktestOptimizationRead,
    BacktestResearchReportRead,
    BacktestRunRead,
    BacktestRunRequest,
    PortfolioBacktestRead,
    PortfolioBacktestRequest,
)

router = APIRouter(prefix="/backtest")
service = BacktestService()
job_registry = BacktestJobRegistry()
portfolio_job_registry = BacktestJobRegistry(prefix="portfolio-backtest", job_kind="portfolio")
optimization_job_registry = BacktestJobRegistry(prefix="backtest-optimization", job_kind="optimization")


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


@router.post("/portfolio/jobs", response_model=BacktestJobRead)
def submit_portfolio_backtest_job(
    payload: PortfolioBacktestRequest,
    current_user: User = Depends(get_current_active_user),
) -> BacktestJobRead:
    job_payload = payload.model_dump(mode="json")
    job_payload["tenant_id"] = settings.default_tenant_id
    job_payload["user_id"] = current_user.id
    job = portfolio_job_registry.submit(job_payload)
    return BacktestJobRead(**job)


@router.get("/portfolio/jobs/{job_id}", response_model=BacktestJobRead)
def get_portfolio_backtest_job(job_id: str, current_user: User = Depends(get_current_active_user)) -> BacktestJobRead:
    job = portfolio_job_registry.get(job_id)
    if job is None or int((job.get("payload") or {}).get("user_id") or 0) != current_user.id:
        raise HTTPException(status_code=404, detail="portfolio backtest job not found")
    return BacktestJobRead(**job)


@router.post("/optimizations/jobs", response_model=BacktestOptimizationJobRead)
def submit_backtest_optimization_job(
    payload: BacktestOptimizationRequest,
    current_user: User = Depends(get_current_active_user),
) -> BacktestOptimizationJobRead:
    job_payload = payload.model_dump(mode="json")
    job_payload["tenant_id"] = settings.default_tenant_id
    job_payload["user_id"] = current_user.id
    job = optimization_job_registry.submit(job_payload)
    return BacktestOptimizationJobRead(**job)


@router.get("/optimizations/jobs/latest", response_model=BacktestOptimizationJobRead)
def get_latest_backtest_optimization_job(current_user: User = Depends(get_current_active_user)) -> BacktestOptimizationJobRead:
    job = optimization_job_registry.latest(current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="backtest optimization job not found")
    return BacktestOptimizationJobRead(**job)


@router.get("/optimizations/jobs/{job_id}", response_model=BacktestOptimizationJobRead)
def get_backtest_optimization_job(job_id: str, current_user: User = Depends(get_current_active_user)) -> BacktestOptimizationJobRead:
    job = optimization_job_registry.get(job_id)
    if job is None or int((job.get("payload") or {}).get("user_id") or 0) != current_user.id:
        raise HTTPException(status_code=404, detail="backtest optimization job not found")
    return BacktestOptimizationJobRead(**job)


@router.get("/optimizations/history", response_model=list[BacktestOptimizationHistoryRead])
def get_backtest_optimization_history(current_user: User = Depends(get_current_active_user)) -> list[BacktestOptimizationHistoryRead]:
    return [BacktestOptimizationHistoryRead(**item) for item in optimization_job_registry.history(current_user.id)]


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


@router.post("/research-report", response_model=BacktestResearchReportRead)
def build_research_report(
    payload: BacktestRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BacktestResearchReportRead:
    result = service.run_single_symbol_backtest(db, tenant_id=settings.default_tenant_id, user_id=current_user.id, **payload.model_dump())
    report = ((result.get("summary") or {}).get("research_report") or {}) if isinstance(result, dict) else {}
    if not report:
        reason = str(((result.get("summary") or {}).get("reason") or "no_records") if isinstance(result, dict) else "no_records")
        symbol = str(result.get("symbol") or payload.symbol) if isinstance(result, dict) else payload.symbol
        report = {
            "format": "markdown",
            "content": f"# {symbol} 回测研究报告\n\n暂无可用于生成研究报告的历史数据。\n\n原因：{reason}",
        }
    return BacktestResearchReportRead(**report)


@router.post("/portfolio/run", response_model=PortfolioBacktestRead)
def run_portfolio_backtest(
    payload: PortfolioBacktestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PortfolioBacktestRead:
    result = service.run_portfolio_backtest(db, tenant_id=settings.default_tenant_id, user_id=current_user.id, **payload.model_dump())
    return PortfolioBacktestRead(**result)


@router.post("/daily-review", response_model=BacktestDailyReviewRead)
def build_daily_review(
    payload: BacktestDailyReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BacktestDailyReviewRead:
    result = service.build_daily_review(db, tenant_id=settings.default_tenant_id, user_id=current_user.id, **payload.model_dump())
    return BacktestDailyReviewRead(**result)
