from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from kombu.exceptions import OperationalError as KombuOperationalError
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.smart_selection import (
    SmartSelectionConfigRead,
    SmartSelectionConfigUpdate,
    SmartSelectionFactorRankItemRead,
    SmartSelectionFactorRankRead,
    SmartSelectionFactorRankRequest,
    SmartSelectionEvaluationRead,
    SmartSelectionHistoryRead,
    SmartSelectionLatestRead,
    SmartSelectionRunDispatchRead,
)
from app.smart_selection.evaluation import SmartSelectionScoringEvaluator
from app.smart_selection.service import SmartSelectionService
from app.tasks.smart_selection_tasks import run_smart_selection_task

router = APIRouter(prefix="/smart-selection")
service = SmartSelectionService()


def _is_broker_unavailable_error(error: Exception) -> bool:
    if isinstance(error, (KombuOperationalError, OSError, TimeoutError)):
        return True
    return any(
        marker in str(error).lower()
        for marker in (
            "connection refused",
            "connection is bad",
            "redis",
            "broker",
            "temporarily unavailable",
            "operation not permitted",
        )
    )


@router.get("/config", response_model=SmartSelectionConfigRead)
def get_smart_selection_config(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> SmartSelectionConfigRead:
    return service.get_config(db, settings.default_tenant_id, current_user.id)


@router.put("/config", response_model=SmartSelectionConfigRead)
def update_smart_selection_config(
    payload: SmartSelectionConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SmartSelectionConfigRead:
    return service.update_config(db, settings.default_tenant_id, payload, current_user.id)


@router.get("/latest", response_model=SmartSelectionLatestRead)
def get_latest_smart_selection(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> SmartSelectionLatestRead:
    return service.get_latest_snapshot(db, settings.default_tenant_id, current_user.id)


@router.get("/history", response_model=SmartSelectionHistoryRead)
def get_smart_selection_history(limit: int = 10, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> SmartSelectionHistoryRead:
    safe_limit = min(max(limit, 1), 30)
    return SmartSelectionHistoryRead(runs=service.list_history(db, settings.default_tenant_id, limit=safe_limit, user_id=current_user.id))


@router.get("/runs/{run_id}/evaluation", response_model=SmartSelectionEvaluationRead)
def evaluate_smart_selection_run(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> SmartSelectionEvaluationRead:
    try:
        result = SmartSelectionScoringEvaluator(db).evaluate_run(run_id, user_id=current_user.id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return SmartSelectionEvaluationRead(**result)


@router.post("/run", response_model=SmartSelectionRunDispatchRead)
def trigger_smart_selection_run(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> SmartSelectionRunDispatchRead:
    run = service.create_run(db, tenant_id=settings.default_tenant_id, triggered_by="manual", user_id=current_user.id)
    try:
        result = run_smart_selection_task.apply_async(
            kwargs={"run_id": run.id, "triggered_by": "manual", "tenant_id": settings.default_tenant_id, "user_id": current_user.id}
        )
    except Exception as error:
        service.fail_run(db, run.id, error_message=str(error))
        if _is_broker_unavailable_error(error):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="消息队列不可用，请检查 Redis / Celery broker 后重试",
            ) from error
        raise
    service.mark_run_queued(db, run.id, task_id=result.id)
    return SmartSelectionRunDispatchRead(status="queued", run_id=run.id, task_id=result.id)


@router.post("/factors/rank", response_model=SmartSelectionFactorRankRead)
def rank_smart_selection_factors(
    payload: SmartSelectionFactorRankRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SmartSelectionFactorRankRead:
    ranked = service.rank_factors(
        db,
        payload.symbols,
        factor=payload.factor,
        source=payload.source,
        adjustflag=payload.adjustflag,
        limit=payload.limit,
    )
    return SmartSelectionFactorRankRead(
        factor=payload.factor,
        source=payload.source,
        adjustflag=payload.adjustflag,
        items=[
            SmartSelectionFactorRankItemRead(
                symbol=item.symbol,
                factor=item.factor,
                value=item.value,
                rank=item.rank,
                missing_reason=item.missing_reason,
                missing_ratio=item.missing_ratio,
                computable=item.computable,
                source_fields=list(item.source_fields),
            )
            for item in ranked
        ],
    )
