import logging

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.smart_selection.service import SmartSelectionService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.smart_selection_tasks.run_smart_selection_task", bind=True)
def run_smart_selection_task(
    self,
    run_id: int | None = None,
    triggered_by: str = "system",
    tenant_id: str = "local",
    user_id: int | None = None,
) -> dict[str, object]:
    service = SmartSelectionService()
    logger.info(
        "Celery task started task=%s task_id=%s run_id=%s triggered_by=%s tenant_id=%s user_id=%s",
        self.name,
        self.request.id,
        run_id,
        triggered_by,
        tenant_id,
        user_id,
    )
    with SessionLocal() as db:
        try:
            run = service.execute_run(
                db,
                run_id=run_id,
                task_id=self.request.id,
                triggered_by=triggered_by,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        except TypeError:
            run = service.execute_run(
                db,
                run_id=run_id,
                task_id=self.request.id,
                triggered_by=triggered_by,
                tenant_id=tenant_id,
            )

    result = {
        "status": "completed",
        "task": "run_smart_selection",
        "run_id": run.id,
        "task_id": self.request.id,
        "recommendation_count": run.recommendation_count,
    }
    logger.info(
        "Celery task succeeded task=%s task_id=%s run_id=%s count=%s",
        self.name,
        self.request.id,
        run.id,
        run.recommendation_count,
    )
    return result
