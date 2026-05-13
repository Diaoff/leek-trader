from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SignalAction = Literal["buy", "sell", "reduce", "hold"]


@dataclass(frozen=True, slots=True)
class OrderIntent:
    side: Literal["buy", "sell", "none"]
    target_position_pct: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RiskIntent:
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    requires_confirmation: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StrategySignal:
    symbol: str
    strategy: str
    action: SignalAction
    strength: str = "weak"
    trigger_reason: str = ""
    position_pct: float = 0.0
    confidence: float | None = None
    order_intent: OrderIntent | None = None
    risk_intent: RiskIntent = field(default_factory=RiskIntent)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def coerce(cls, payload: "StrategySignal | dict[str, Any]") -> "StrategySignal":
        return payload if isinstance(payload, StrategySignal) else cls.from_legacy(payload)

    @classmethod
    def from_legacy(cls, payload: dict[str, Any]) -> "StrategySignal":
        action = str(payload.get("signal") or "hold")
        if action not in {"buy", "sell", "reduce", "hold"}:
            action = "hold"
        position_pct = _clamp_fraction(payload.get("position_pct"), default=0.0)
        trigger_reason = str(payload.get("trigger_reason") or "")
        side = "buy" if action == "buy" else "sell" if action in {"sell", "reduce"} else "none"
        return cls(
            symbol=str(payload.get("symbol") or ""),
            strategy=str(payload.get("strategy") or "unknown"),
            action=action,  # type: ignore[arg-type]
            strength=str(payload.get("strength") or "weak"),
            trigger_reason=trigger_reason,
            position_pct=position_pct,
            confidence=_optional_float(payload.get("confidence")),
            order_intent=OrderIntent(side=side, target_position_pct=position_pct, reason=trigger_reason),
            risk_intent=RiskIntent(
                stop_loss_price=_optional_float(payload.get("stop_loss_price")),
                take_profit_price=_optional_float(payload.get("take_profit_price")),
                requires_confirmation=bool(payload.get("requires_recommendation_confirmation") or False),
            ),
            metadata={key: value for key, value in payload.items() if key not in _LEGACY_CORE_KEYS},
        )

    def to_legacy(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "signal": self.action,
            "strength": self.strength,
            "trigger_reason": self.trigger_reason,
            "position_pct": self.position_pct,
            "stop_loss_price": self.risk_intent.stop_loss_price,
            "take_profit_price": self.risk_intent.take_profit_price,
            "requires_recommendation_confirmation": self.risk_intent.requires_confirmation,
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        payload.update(self.metadata)
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["legacy"] = self.to_legacy()
        return payload


_LEGACY_CORE_KEYS = {
    "symbol",
    "strategy",
    "signal",
    "strength",
    "trigger_reason",
    "position_pct",
    "confidence",
    "stop_loss_price",
    "take_profit_price",
    "requires_recommendation_confirmation",
}


def _optional_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _clamp_fraction(value: object, *, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(numeric, 1.0))
