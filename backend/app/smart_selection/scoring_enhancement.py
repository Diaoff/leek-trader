from __future__ import annotations

from typing import Any

from app.smart_selection.evaluation import ForwardPerformance, SmartSelectionScoringEvaluator

SCORE_VERSION = "smart-selection-enhanced/v1"
DEFAULT_FACTOR_WEIGHTS = {
    "trend": 1.0,
    "fund_flow": 1.0,
    "k_pattern": 1.0,
    "nine_turn": 1.0,
    "lhb": 1.0,
    "hot_sectors": 1.0,
    "market": 1.0,
    "liquidity": 1.0,
    "risk_reward": 1.0,
}


class SmartSelectionScoreEnhancer:
    @classmethod
    def enhance(cls, *, base_score: float, dimension_scores: dict[str, Any], risk_reward: float, market_state: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
        weights = cls._factor_weights(config=config, market_state=market_state or {})
        contributions = {
            "trend": cls._weighted_delta(dimension_scores.get("trend"), 20.0, weights["trend"], 4.0),
            "fund_flow": cls._weighted_delta(dimension_scores.get("fund_flow"), 25.0, weights["fund_flow"], 5.0),
            "k_pattern": cls._weighted_delta(dimension_scores.get("k_pattern"), 25.0, weights["k_pattern"], 5.0),
            "nine_turn": cls._weighted_delta(dimension_scores.get("nine_turn"), 15.0, weights["nine_turn"], 3.0),
            "lhb": cls._weighted_delta(dimension_scores.get("lhb"), 10.0, weights["lhb"], 2.0),
            "hot_sectors": cls._weighted_delta(dimension_scores.get("hot_sectors"), 5.0, weights["hot_sectors"], 2.0),
            "market": cls._market_contribution(dimension_scores.get("market"), weights["market"]),
            "liquidity": cls._weighted_delta(dimension_scores.get("liquidity"), 8.0, weights["liquidity"], 2.0),
            "risk_reward": cls._risk_reward_contribution(risk_reward, weights["risk_reward"]),
        }
        score_delta = round(sum(contributions.values()), 2)
        enhanced_score = round(max(0.0, min(120.0, base_score + score_delta)), 1)
        return {
            "score_version": SCORE_VERSION,
            "base_score": round(base_score, 1),
            "enhanced_score": enhanced_score,
            "score_delta": round(enhanced_score - base_score, 2),
            "factor_weights": weights,
            "score_explain": {key: round(value, 2) for key, value in contributions.items() if abs(value) >= 0.01},
        }

    @staticmethod
    def _factor_weights(*, config: dict[str, Any], market_state: dict[str, Any]) -> dict[str, float]:
        configured = config.get("scoring_enhancement", {}).get("factor_weights", {})
        weights = {key: float(configured.get(key, value)) for key, value in DEFAULT_FACTOR_WEIGHTS.items()}
        regime = market_state.get("regime")
        if regime == "strong":
            weights["trend"] *= 1.1
            weights["fund_flow"] *= 1.1
            weights["risk_reward"] *= 0.9
        elif regime == "weak":
            weights["market"] *= 1.2
            weights["liquidity"] *= 1.1
            weights["risk_reward"] *= 1.2
        return {key: round(value, 4) for key, value in weights.items()}

    @staticmethod
    def _weighted_delta(value: Any, cap: float, weight: float, scale: float) -> float:
        normalized = max(0.0, min(cap, float(value or 0.0))) / cap if cap else 0.0
        return (normalized - 0.5) * scale * weight

    @staticmethod
    def _market_contribution(value: Any, weight: float) -> float:
        return max(-4.0, min(4.0, float(value or 0.0) * 0.4 * weight))

    @staticmethod
    def _risk_reward_contribution(risk_reward: float, weight: float) -> float:
        return max(-4.0, min(5.0, (float(risk_reward or 0.0) - 1.0) * 2.0 * weight))


__all__ = [
    "DEFAULT_FACTOR_WEIGHTS",
    "ForwardPerformance",
    "SCORE_VERSION",
    "SmartSelectionScoreEnhancer",
    "SmartSelectionScoringEvaluator",
]
