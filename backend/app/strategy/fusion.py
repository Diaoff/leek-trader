from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WeightedSignal:
    source: str
    signal: str
    strength: str
    weight: float
    confidence: float
    reason: str
    payload: dict[str, Any]


class SignalFusionService:
    _DIRECTION_SCORE = {
        "buy": 1.0,
        "reduce": -0.5,
        "sell": -1.0,
        "hold": 0.0,
    }
    _STRENGTH_CONFIDENCE = {
        "strong": 1.0,
        "normal": 0.75,
        "weak": 0.45,
    }

    def fuse(self, signals: list[WeightedSignal], *, min_confidence: float = 0.55, conflict_hold_threshold: float = 0.2) -> dict[str, Any]:
        if not signals:
            return {
                "signal": "hold",
                "strength": "weak",
                "trigger_reason": "fusion_no_components",
                "fusion_score": 0.0,
                "fusion_confidence": 0.0,
                "component_signals": [],
            }

        total_weight = sum(max(signal.weight, 0.0) for signal in signals) or 1.0
        weighted_score = sum(self._DIRECTION_SCORE.get(signal.signal, 0.0) * signal.weight * signal.confidence for signal in signals) / total_weight
        confidence = sum(signal.weight * signal.confidence for signal in signals) / total_weight
        component_signals = [
            {
                "source": signal.source,
                "signal": signal.signal,
                "strength": signal.strength,
                "weight": signal.weight,
                "confidence": signal.confidence,
                "reason": signal.reason,
                "payload": signal.payload,
            }
            for signal in signals
        ]

        if confidence < min_confidence:
            action = "hold"
            strength = "weak"
            reason = "fusion_low_confidence"
        elif abs(weighted_score) < conflict_hold_threshold:
            action = "hold"
            strength = "weak"
            reason = "fusion_conflicting_signals"
        elif weighted_score > 0:
            action = "buy"
            strength = "strong" if weighted_score >= 0.7 else "normal"
            reason = "fusion_weighted_buy"
        elif weighted_score <= -0.7:
            action = "sell"
            strength = "strong"
            reason = "fusion_weighted_sell"
        else:
            action = "reduce"
            strength = "normal"
            reason = "fusion_weighted_reduce"

        return {
            "signal": action,
            "strength": strength,
            "trigger_reason": reason,
            "fusion_score": round(weighted_score, 4),
            "fusion_confidence": round(confidence, 4),
            "component_signals": component_signals,
        }

    @classmethod
    def confidence_for(cls, signal: dict[str, Any]) -> float:
        strength = str(signal.get("strength") or "weak")
        if "confidence" in signal:
            try:
                return max(0.0, min(float(signal["confidence"]), 1.0))
            except (TypeError, ValueError):
                pass
        return cls._STRENGTH_CONFIDENCE.get(strength, 0.45)
