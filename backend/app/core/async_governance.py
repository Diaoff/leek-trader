from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AsyncTaskGovernance:
    key: str
    idempotency_scope: str
    duplicate_policy: str
    retry_safety: str
    side_effects: list[str]
    idempotency_fields: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "idempotency_scope": self.idempotency_scope,
            "duplicate_policy": self.duplicate_policy,
            "retry_safety": self.retry_safety,
            "side_effects": self.side_effects,
            "idempotency_fields": self.idempotency_fields,
            "notes": self.notes,
        }


TASK_GOVERNANCE: dict[str, AsyncTaskGovernance] = {
    "refresh_market_quotes": AsyncTaskGovernance(
        key="refresh_market_quotes",
        idempotency_scope="symbols + scheduled flag",
        duplicate_policy="safe_refresh",
        retry_safety="safe",
        side_effects=["quote cache update"],
        idempotency_fields=["symbols", "scheduled"],
        notes=["重复执行只刷新最新报价，不创建业务记录。"],
    ),
    "run_smart_selection": AsyncTaskGovernance(
        key="run_smart_selection",
        idempotency_scope="run_id when present; tenant/user/trigger otherwise",
        duplicate_policy="run_record_guarded",
        retry_safety="guarded",
        side_effects=["smart selection run status", "recommendation snapshot"],
        idempotency_fields=["run_id", "tenant_id", "user_id", "triggered_by"],
        notes=["优先传入 run_id；重试应回写同一 run 记录，避免生成多份推荐快照。"],
    ),
    "run_strategy_cycle": AsyncTaskGovernance(
        key="run_strategy_cycle",
        idempotency_scope="strategy_ids + user_id + scheduler interval gate",
        duplicate_policy="interval_guarded_for_scheduled_runs",
        retry_safety="guarded",
        side_effects=["strategy run records", "optional paper orders"],
        idempotency_fields=["strategy_ids", "user_id", "scheduled"],
        notes=["定时任务受策略调度间隔保护；手动触发可能产生新的运行记录。"],
    ),
    "match_pending_orders": AsyncTaskGovernance(
        key="match_pending_orders",
        idempotency_scope="pending order status",
        duplicate_policy="state_transition_guarded",
        retry_safety="safe",
        side_effects=["order status", "trades", "positions", "cash flows"],
        idempotency_fields=["scheduled"],
        notes=["只处理仍处于 pending 的委托；已成交/已撤单委托不会重复撮合。"],
    ),
    "monitor_position_guards": AsyncTaskGovernance(
        key="monitor_position_guards",
        idempotency_scope="active position guards",
        duplicate_policy="state_transition_guarded",
        retry_safety="guarded",
        side_effects=["guard-triggered paper orders", "position guard state"],
        idempotency_fields=["scheduled"],
        notes=["重复巡检依赖持仓和 guard 状态保护；极端并发下应优先检查未触发状态。"],
    ),
}


def stable_payload_hash(payload: dict[str, Any] | None) -> str:
    normalized = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def build_task_idempotency_key(task_key: str, payload: dict[str, Any] | None = None) -> str:
    governance = TASK_GOVERNANCE.get(task_key)
    source_payload = payload or {}
    if governance is None:
        scoped_payload = source_payload
    else:
        scoped_payload = {field: source_payload.get(field) for field in governance.idempotency_fields if field in source_payload}
    return f"{task_key}:{stable_payload_hash(scoped_payload)}"


def get_task_governance(task_key: str) -> dict[str, object]:
    governance = TASK_GOVERNANCE.get(task_key)
    if governance is None:
        return {
            "key": task_key,
            "idempotency_scope": "unspecified",
            "duplicate_policy": "manual_review_required",
            "retry_safety": "unknown",
            "side_effects": [],
            "idempotency_fields": [],
            "notes": ["该任务尚未登记幂等与重试边界。"],
        }
    return governance.to_dict()
