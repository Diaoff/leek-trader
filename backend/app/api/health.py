from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, object]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "tenant": settings.default_tenant_id,
        "services": {
            "api": "up",
            "database": "configured",
            "redis": "configured",
        },
    }
