from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RLActionType = Literal["hold", "buy", "sell"]
RLActionEncoding = Literal["legacy_zero_based", "rl_stock_one_based"]


@dataclass(slots=True)
class RLAction:
    action_type: RLActionType
    target_position_pct: float = 0.0


class RLActionDecoder:
    @staticmethod
    def decode(action: RLAction | dict[str, Any] | tuple[float, float] | list[float], *, encoding: RLActionEncoding = "legacy_zero_based") -> RLAction:
        if isinstance(action, RLAction):
            return action
        try:
            if isinstance(action, dict):
                return RLAction(
                    action_type=RLActionDecoder._normalize_action_type(str(action.get("action_type") or "hold")),
                    target_position_pct=RLActionDecoder._clamp_pct(RLActionDecoder._to_float(action.get("target_position_pct"), default=0.0)),
                )
            if isinstance(action, (tuple, list)) and len(action) >= 2:
                raw_type = RLActionDecoder._to_float(action[0], default=3.0)
                if encoding == "rl_stock_one_based":
                    rounded_type = int(raw_type)
                    amount = RLActionDecoder._clamp_pct(RLActionDecoder._to_float(action[1], default=0.0))
                    if rounded_type == 1:
                        action_type = "buy"
                        target_position_pct = amount
                    elif rounded_type == 2:
                        action_type = "sell"
                        target_position_pct = 1.0 - amount
                    else:
                        action_type = "hold"
                        target_position_pct = 0.0
                    return RLAction(action_type=action_type, target_position_pct=target_position_pct)
                if raw_type < 1:
                    action_type: RLActionType = "buy"
                elif raw_type < 2:
                    action_type = "sell"
                else:
                    action_type = "hold"
                return RLAction(action_type=action_type, target_position_pct=RLActionDecoder._clamp_pct(RLActionDecoder._to_float(action[1], default=0.0)))
        except (TypeError, ValueError):
            return RLAction(action_type="hold", target_position_pct=0.0)
        return RLAction(action_type="hold", target_position_pct=0.0)

    @staticmethod
    def _normalize_action_type(value: str) -> RLActionType:
        normalized = value.strip().lower()
        if normalized in {"buy", "sell", "hold"}:
            return normalized  # type: ignore[return-value]
        return "hold"

    @staticmethod
    def _clamp_pct(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _to_float(value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
