from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.models.user import User


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    user_id: int | None = None
    is_superuser: bool = False


def get_local_tenant_context(user: User | None = None) -> TenantContext:
    tenant_id = settings.default_tenant_id
    if user is None:
        return TenantContext(tenant_id=tenant_id)
    return TenantContext(
        tenant_id=user.tenant_id or tenant_id,
        user_id=user.id,
        is_superuser=bool(user.is_superuser),
    )


def assert_local_tenant_scope(tenant_id: str) -> None:
    if tenant_id != settings.default_tenant_id:
        raise ValueError("Only the configured local tenant scope is supported")
