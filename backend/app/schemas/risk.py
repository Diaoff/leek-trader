from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RiskSeverity(StrEnum):
    HARD = "hard"
    WARN = "warn"
    INFO = "info"


class RiskDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    REJECT = "reject"


class RiskCheckResult(BaseModel):
    rule_id: str
    passed: bool
    severity: RiskSeverity = RiskSeverity.HARD
    suggested_action: str | None = None
    explanation: str | None = None
    threshold: bool | int | float | str | None = None
    actual: bool | int | float | str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    rule_version: str | None = None

    def is_triggered_warning(self) -> bool:
        return self.severity == RiskSeverity.WARN and bool(self.metadata.get("triggered"))

    def legacy_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.rule_id,
            "rule_id": self.rule_id,
            "passed": self.passed,
            "severity": self.severity.value,
            "suggested_action": self.suggested_action,
            "explanation": self.explanation,
            "reason": None if self.passed and not self.is_triggered_warning() else self.explanation,
            "threshold": self._serialize_scalar(self.threshold),
            "actual": self._serialize_scalar(self.actual),
            "metadata": self.metadata,
            "rule_version": self.rule_version,
        }
        for key, value in self.metadata.items():
            if key not in payload:
                payload[key] = self._serialize_scalar(value)
        return payload

    @staticmethod
    def _serialize_scalar(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        return value


class RiskEvaluationResult(BaseModel):
    passed: bool
    decision: RiskDecision = RiskDecision.PASS
    checks: list[RiskCheckResult] = Field(default_factory=list)
    rejection_reason: str | None = None
    risk_rule_version: str | None = None

    def legacy_checks(self) -> list[dict[str, Any]]:
        return [check.legacy_dict() for check in self.checks]
