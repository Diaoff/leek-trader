from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SignalAction = Literal["buy", "sell", "reduce", "hold"]
ExecutionEnvironment = Literal["paper", "backtest", "live", "research"]
TemplateCategory = Literal["breakout", "mean_reversion", "momentum", "grid", "factor_scoring", "portfolio_rebalance"]


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
class StrategyContext:
    environment: ExecutionEnvironment
    execution_mode: str
    available_cash: float | None = None
    position_value: float | None = None
    total_equity: float | None = None
    position_symbols: tuple[str, ...] = ()
    paper_trading: bool = True
    backtest: bool = False
    strategy_parameters: dict[str, Any] = field(default_factory=dict)
    minimum_history: int = 0
    history_ready: bool = False
    history_available: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ParameterConstraint:
    key: str
    type: str
    minimum: float | None = None
    maximum: float | None = None
    inclusive_minimum: bool = True
    inclusive_maximum: bool = True
    default: Any = None
    enum: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StrategyMetadata:
    strategy_type: str
    display_name: str
    template_category: TemplateCategory
    minimum_history: int
    supported_execution_modes: tuple[str, ...]
    parameter_schema: tuple[ParameterConstraint, ...] = ()
    risk_note: str = ""
    mode_note: str = ""
    auto_trade_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["parameter_schema"] = [item.to_dict() for item in self.parameter_schema]
        return payload


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
        payload["order_intent"] = self.order_intent.to_dict() if self.order_intent is not None else None
        payload["risk_intent"] = self.risk_intent.to_dict()
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
