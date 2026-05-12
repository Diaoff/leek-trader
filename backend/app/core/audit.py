from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.logging import audit_logger


def _safe_details(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    redacted: dict[str, Any] = {}
    for key, value in details.items():
        lowered = key.lower()
        if any(marker in lowered for marker in ("password", "token", "secret", "api_key", "cookie")):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def audit_event(
    action: str,
    *,
    actor_id: int | None = None,
    actor_name: str | None = None,
    tenant_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "tenant_id": tenant_id,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id is not None else None,
        "outcome": outcome,
        "details": _safe_details(details),
    }
    audit_logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return payload
