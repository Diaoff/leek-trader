import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.preferences import TradingPreferences


RISK_RULE_VERSION_PREFIX = "risk-rules"
RISK_RULE_VERSION_SCHEMA = 1


class RiskRuleVersion(BaseModel):
    version: str
    schema_version: int = RISK_RULE_VERSION_SCHEMA
    threshold_snapshot: dict[str, int | float]
    change_source: str = "trading_preferences"
    changed_at: str
    description: str = "当前风控规则由交易偏好阈值生成，版本号随阈值快照变化。"
    notes: list[str] = Field(default_factory=list)


class RiskRuleVersionService:
    tracked_thresholds = (
        "max_daily_trades",
        "single_position_limit_pct",
        "total_exposure_limit_pct",
        "daily_loss_limit_pct",
    )

    def current_version(
        self,
        preferences: TradingPreferences,
        *,
        changed_at: datetime | str | None = None,
        change_source: str = "trading_preferences",
        description: str | None = None,
    ) -> RiskRuleVersion:
        snapshot = self.threshold_snapshot(preferences)
        return RiskRuleVersion(
            version=self.version_id(snapshot),
            threshold_snapshot=snapshot,
            change_source=change_source,
            changed_at=self._serialize_changed_at(changed_at),
            description=description or "当前风控规则由交易偏好阈值生成，版本号随阈值快照变化。",
            notes=[
                "覆盖日交易次数、单标的仓位、总敞口和日亏损熔断阈值。",
                "订单风控结果会携带该版本，便于回溯拒单来源。",
            ],
        )

    def threshold_snapshot(self, preferences: TradingPreferences) -> dict[str, int | float]:
        payload = preferences.model_dump()
        return {key: payload[key] for key in self.tracked_thresholds}

    def version_id(self, snapshot: dict[str, Any]) -> str:
        canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        return f"{RISK_RULE_VERSION_PREFIX}-v{RISK_RULE_VERSION_SCHEMA}-{digest}"

    @staticmethod
    def _serialize_changed_at(changed_at: datetime | str | None) -> str:
        if isinstance(changed_at, str):
            return changed_at
        if changed_at is None:
            changed_at = datetime.now(timezone.utc)
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        return changed_at.isoformat()
