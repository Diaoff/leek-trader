from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from kombu.exceptions import OperationalError as KombuOperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.schemas.smart_selection import (
    SmartSelectionConfigRead,
    SmartSelectionConfigUpdate,
    SmartSelectionHistoryRead,
    SmartSelectionLatestRead,
    SmartSelectionRunDispatchRead,
)
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
def get_smart_selection_config(db: Session = Depends(get_db)) -> SmartSelectionConfigRead:
    return service.get_config(db, settings.default_tenant_id)


@router.put("/config", response_model=SmartSelectionConfigRead)
def update_smart_selection_config(
    payload: SmartSelectionConfigUpdate,
    db: Session = Depends(get_db),
) -> SmartSelectionConfigRead:
    return service.update_config(db, settings.default_tenant_id, payload)


@router.get("/latest", response_model=SmartSelectionLatestRead)
def get_latest_smart_selection(db: Session = Depends(get_db)) -> SmartSelectionLatestRead:
    return service.get_latest_snapshot(db, settings.default_tenant_id)


@router.get("/history", response_model=SmartSelectionHistoryRead)
def get_smart_selection_history(limit: int = 10, db: Session = Depends(get_db)) -> SmartSelectionHistoryRead:
    safe_limit = min(max(limit, 1), 30)
    return SmartSelectionHistoryRead(runs=service.list_history(db, settings.default_tenant_id, limit=safe_limit))


@router.post("/run", response_model=SmartSelectionRunDispatchRead)
def trigger_smart_selection_run(db: Session = Depends(get_db)) -> SmartSelectionRunDispatchRead:
    run = service.create_run(db, tenant_id=settings.default_tenant_id, triggered_by="manual")
    try:
        result = run_smart_selection_task.apply_async(
            kwargs={"run_id": run.id, "triggered_by": "manual", "tenant_id": settings.default_tenant_id}
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
