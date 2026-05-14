from __future__ import annotations

from typing import Any, Literal
from pathlib import Path

from app.market.providers.base import DailyBarSnapshot
from app.quant.actions import RLAction, RLActionDecoder
from app.quant.exits import RLExitLevelAdvisor
from app.quant.features import build_rl_state, daily_bar_to_rl_record
from app.quant.simulator import RLEpisodeConfig, RLEpisodeSimulator
from app.quant.ppo_training import PPO_ALGORITHM, predict_ppo_action
from app.quant.training import RLModelRegistry
from app.strategy.base import StrategyPlugin
from app.strategy.contracts import ParameterConstraint, StrategyMetadata, StrategySignal
from app.strategy.signals import signal_from_payload

RLPolicyMode = Literal["baseline", "replay", "external_stub", "trained_model"]


class RLTradingStrategy(StrategyPlugin):
    name = "rl_trading"
    metadata = StrategyMetadata(
        strategy_type=name,
        display_name="RL 实验",
        template_category="portfolio_rebalance",
        minimum_history=45,
        supported_execution_modes=("signal_only",),
        parameter_schema=(
            ParameterConstraint("rl_policy_mode", "string", default="baseline", enum=("baseline", "replay", "external_stub", "trained_model"), description="策略模式"),
            ParameterConstraint("max_position_pct", "number", minimum=0, maximum=1, default=0.5, description="最大仓位"),
            ParameterConstraint("min_confidence", "number", minimum=0, maximum=1, default=0.1, description="最低置信度"),
        ),
        risk_note="仅在模型 validated/active 且训练状态合格时才可候选",
        mode_note="仅建议实验观察，默认不进入自动交易",
        auto_trade_allowed=False,
    )

    def minimum_history(self, parameters: dict[str, object]) -> int:
        short_window = max(int(parameters.get("ma_short_window", parameters.get("short_window", 5))), 2)
        long_window = max(int(parameters.get("ma_long_window", parameters.get("long_window", 20))), short_window + 1)
        return max(int(parameters.get("min_history", long_window + 20)), self.metadata.minimum_history)

    def empty_signal(self, symbol: str, parameters: dict | None = None) -> StrategySignal:
        return signal_from_payload(self._build_hold_signal(
            symbol,
            reason="history_unavailable",
            entry_price_ref=None,
            policy_mode=str((parameters or {}).get("rl_policy_mode", "baseline")),
        ))

    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> StrategySignal:
        short_window = max(int(parameters.get("ma_short_window", parameters.get("short_window", 5))), 2)
        long_window = max(int(parameters.get("ma_long_window", parameters.get("long_window", 20))), short_window + 1)
        minimum_bars = max(int(parameters.get("min_history", long_window + 2)), long_window + 2)
        latest_close = self._last_close(bars)
        if len(bars) < minimum_bars:
            return signal_from_payload(self._build_hold_signal(
                symbol,
                reason="insufficient_history",
                entry_price_ref=latest_close,
                policy_mode=str(parameters.get("rl_policy_mode", "baseline")),
            ))

        max_position_pct = self._clamp_fraction(parameters.get("max_position_pct"), default=1.0)
        min_confidence = self._clamp_fraction(parameters.get("min_confidence"), default=0.0)
        policy_mode = self._normalize_policy_mode(parameters.get("rl_policy_mode"))
        action_encoding = "rl_stock_one_based" if parameters.get("action_encoding") == "rl_stock_one_based" else "legacy_zero_based"
        state = build_rl_state(bars, short_window=short_window, long_window=long_window)
        action = self._select_action(state, parameters, policy_mode=policy_mode, action_encoding=action_encoding, bars=bars)
        target_pct = min(action.target_position_pct, max_position_pct)
        signal = self._signal_from_action(action)
        confidence = self._confidence(state, action, policy_mode)
        trigger_reason = self._trigger_reason(policy_mode=policy_mode, action=action, state=state)

        if confidence < min_confidence:
            signal = "hold"
            target_pct = 0.0
            trigger_reason = "min_confidence_not_met"

        entry_price = float(bars[-1].close_price)
        advisor = RLExitLevelAdvisor(
            stop_loss_floor_pct=self._clamp_fraction(parameters.get("stop_loss_floor_pct"), default=0.05),
            take_profit_rr=max(float(parameters.get("take_profit_rr", 2.0) or 2.0), 1.0),
            min_risk_reward_ratio=max(float(parameters.get("min_risk_reward_ratio", 1.0) or 1.0), 0.1),
        )
        exit_levels = advisor.advise(
            entry_price=entry_price,
            current_price=entry_price,
            bars=bars,
            holding_days=int(parameters.get("holding_days", 0) or 0),
            max_unrealized_return_pct=float(parameters.get("max_unrealized_return_pct", 0.0) or 0.0),
        )

        return signal_from_payload({
            "symbol": symbol,
            "strategy": self.name,
            "signal": signal,
            "strength": "strong" if confidence >= 0.75 else "normal" if confidence >= 0.55 else "weak",
            "trigger_reason": trigger_reason,
            "entry_price_ref": round(entry_price, 2),
            "stop_loss_price": exit_levels["suggested_stop_loss_price"],
            "take_profit_price": exit_levels["suggested_take_profit_price"],
            "position_pct": round(target_pct, 6),
            "confidence": round(confidence, 6),
            "market_regime": state["market_regime"],
            "requires_recommendation_confirmation": signal == "buy",
            "rl_state": state,
            "rl_action": {
                "action_type": action.action_type,
                "target_position_pct": round(target_pct, 6),
                "raw_target_position_pct": round(action.target_position_pct, 6),
                "policy_mode": policy_mode,
                "action_encoding": action_encoding,
            },
            **exit_levels,
            "filter_passed": True,
            "filter_reasons": [],
            "trend_ok": state["trend_strength"] >= 0,
            "volume_ok": state["volume_ratio"] >= 0.8,
            "volatility_ok": state["volatility_pct"] <= 12.0,
            "stretch_ok": abs(state["price_ma_long_ratio"] - 1.0) <= 0.18,
            "market_regime_bias": state["market_regime"],
        })

    def replay(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> dict[str, Any]:
        records = [daily_bar_to_rl_record(bar) for bar in bars]
        if not records:
            return RLEpisodeSimulator().simulate([]).to_dict()
        config = RLEpisodeConfig(
            initial_cash=float(parameters.get("initial_cash", 100000.0) or 100000.0),
            commission_rate=float(parameters.get("commission_rate", 0.0003) or 0.0),
            slippage_rate=float(parameters.get("slippage_rate", 0.0002) or 0.0),
            reward_mode=parameters.get("reward_mode", "net_worth_change"),
            max_position_pct=self._clamp_fraction(parameters.get("max_position_pct"), default=1.0),
            ma_short_window=max(int(parameters.get("ma_short_window", 5) or 5), 1),
            ma_long_window=max(int(parameters.get("ma_long_window", 20) or 20), 1),
        )
        policy = "moving_average" if parameters.get("rl_policy_mode") == "baseline" else "cash"
        result = RLEpisodeSimulator(config).simulate(
            records,
            policy_name=policy,
            action_sequence=parameters.get("action_sequence") or [],
            action_encoding="rl_stock_one_based" if parameters.get("action_encoding") == "rl_stock_one_based" else "legacy_zero_based",
        )
        payload = result.to_dict()
        payload["symbol"] = symbol
        return payload

    @staticmethod
    def _select_action(
        state: dict[str, Any],
        parameters: dict,
        *,
        policy_mode: RLPolicyMode,
        action_encoding: str,
        bars: list[DailyBarSnapshot] | None = None,
    ) -> RLAction:
        if policy_mode == "replay":
            sequence = parameters.get("action_sequence") or []
            if sequence:
                return RLActionDecoder.decode(sequence[-1], encoding=action_encoding)  # latest preview action
            return RLAction("hold", 0.0)
        if policy_mode == "external_stub":
            return RLActionDecoder.decode(parameters.get("external_action", {"action_type": "hold", "target_position_pct": 0.0}))
        if policy_mode == "trained_model":
            model_id = str(parameters.get("model_id") or "").strip()
            registry_root = parameters.get("model_registry_root")
            if isinstance(registry_root, str):
                registry_root = Path(registry_root)
            artifact = RLModelRegistry(registry_root).load(model_id) if model_id else None
            if not artifact or artifact.get("status") not in {"validated", "active"}:
                return RLAction("hold", 0.0)
            records = [daily_bar_to_rl_record(bar) for bar in bars or []]
            if not records:
                return RLAction("hold", 0.0)
            try:
                if artifact.get("algorithm") != PPO_ALGORITHM:
                    return RLAction("hold", 0.0, metadata={"fallback_reason": "rl_trained_model_unsupported_algorithm"})
                predicted = predict_ppo_action(artifact, records)
                return RLAction(str(predicted["action_type"]), float(predicted["target_position_pct"]))
            except Exception:
                return RLAction("hold", 0.0, metadata={"fallback_reason": "rl_trained_model_fallback"})
        trend_strength = float(state["trend_strength"])
        buy_threshold = RLTradingStrategy._float_parameter(parameters, "baseline_buy_trend_threshold", default=0.015)
        sell_threshold = -abs(RLTradingStrategy._float_parameter(parameters, "baseline_sell_trend_threshold", default=0.015))
        requires_bullish = bool(parameters.get("baseline_buy_requires_bullish", True))
        if trend_strength >= buy_threshold and (not requires_bullish or state["market_regime"] == "bullish"):
            return RLAction("buy", min(1.0, 0.25 + max(trend_strength, 0.0) * 5))
        if trend_strength <= sell_threshold or state["market_regime"] == "bearish":
            return RLAction("sell", 0.0)
        return RLAction("hold", 0.0)

    @staticmethod
    def _signal_from_action(action: RLAction) -> str:
        if action.action_type == "buy" and action.target_position_pct > 0:
            return "buy"
        if action.action_type == "sell":
            return "sell"
        return "hold"

    @staticmethod
    def _confidence(state: dict[str, Any], action: RLAction, policy_mode: RLPolicyMode) -> float:
        if policy_mode in {"replay", "external_stub", "trained_model"}:
            return 0.5 if action.action_type == "hold" else 0.7
        trend_component = min(abs(float(state["trend_strength"])) * 20, 0.35)
        volatility_penalty = min(float(state["volatility_pct"]) / 100, 0.15)
        volume_component = min(max(float(state["volume_ratio"]) - 1.0, 0.0) * 0.1, 0.1)
        return max(0.0, min(1.0, 0.5 + trend_component + volume_component - volatility_penalty))

    @staticmethod
    def _float_parameter(parameters: dict, key: str, *, default: float) -> float:
        value = parameters.get(key, default)
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _trigger_reason(*, policy_mode: RLPolicyMode, action: RLAction, state: dict[str, Any]) -> str:
        if policy_mode == "replay":
            return "rl_replay_action"
        if policy_mode == "external_stub":
            return "rl_external_stub_action"
        if policy_mode == "trained_model":
            fallback_reason = (action.metadata or {}).get("fallback_reason")
            if fallback_reason:
                return str(fallback_reason)
            return "rl_trained_model_action"
        if action.action_type == "buy":
            return "rl_baseline_bullish_trend"
        if action.action_type == "sell":
            return "rl_baseline_bearish_trend"
        return f"rl_baseline_{state['market_regime']}_hold"

    @staticmethod
    def _build_hold_signal(symbol: str, *, reason: str, entry_price_ref: float | None, policy_mode: str) -> dict[str, object]:
        return {
            "symbol": symbol,
            "strategy": "rl_trading",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": reason,
            "entry_price_ref": entry_price_ref,
            "stop_loss_price": None,
            "take_profit_price": None,
            "position_pct": 0.0,
            "confidence": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
            "rl_state": {},
            "rl_action": {"action_type": "hold", "target_position_pct": 0.0, "policy_mode": policy_mode},
            "filter_passed": True,
            "filter_reasons": [],
            "trend_ok": None,
            "volume_ok": None,
            "volatility_ok": None,
            "stretch_ok": None,
            "market_regime_bias": None,
        }

    @staticmethod
    def _last_close(bars: list[DailyBarSnapshot]) -> float | None:
        return round(float(bars[-1].close_price), 2) if bars else None

    @staticmethod
    def _clamp_fraction(value: object, *, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(numeric, 1.0))

    @staticmethod
    def _normalize_policy_mode(value: object) -> RLPolicyMode:
        normalized = str(value or "baseline").strip().lower()
        if normalized in {"baseline", "replay", "external_stub", "trained_model"}:
            return normalized  # type: ignore[return-value]
        return "baseline"
