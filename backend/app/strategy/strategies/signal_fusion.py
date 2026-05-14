from __future__ import annotations

from typing import Any

from app.market.providers.base import DailyBarSnapshot
from app.strategy.base import StrategyPlugin
from app.strategy.contracts import ParameterConstraint, StrategyMetadata, StrategySignal
from app.strategy.fusion import SignalFusionService, WeightedSignal
from app.strategy.signals import clamp_fraction, hold_strategy_signal, risk_prices, signal_from_payload
from app.strategy.strategies.bollinger_band import BollingerBandStrategy
from app.strategy.strategies.kdj_momentum import KdjMomentumStrategy
from app.strategy.strategies.rsi_reversal import RsiReversalStrategy


class SignalFusionStrategy(StrategyPlugin):
    name = "signal_fusion"
    metadata = StrategyMetadata(
        strategy_type=name,
        display_name="多信号融合",
        template_category="factor_scoring",
        minimum_history=35,
        supported_execution_modes=("signal_only",),
        parameter_schema=(
            ParameterConstraint("min_confidence", "number", minimum=0, maximum=1, default=0.55, description="最小置信度"),
            ParameterConstraint("conflict_hold_threshold", "number", minimum=0, maximum=1, default=0.2, description="冲突观望阈值"),
            ParameterConstraint("position_pct", "number", minimum=0, maximum=1, default=0.1, description="最大仓位"),
        ),
        risk_note="融合权重不可视为收益保证，冲突信号会自动观望",
        mode_note="按可解释权重融合多个指标信号，默认仅信号观察",
        auto_trade_allowed=False,
    )
    _COMPONENTS: dict[str, StrategyPlugin] = {
        "rsi_reversal": RsiReversalStrategy(),
        "bollinger_band": BollingerBandStrategy(),
        "kdj_momentum": KdjMomentumStrategy(),
    }

    def __init__(self) -> None:
        self.fusion_service = SignalFusionService()

    def minimum_history(self, parameters: dict[str, Any]) -> int:
        components = self._components(parameters)
        component_limits = []
        for component in components:
            plugin = self._COMPONENTS.get(str(component.get("strategy_type") or ""))
            if plugin is None:
                continue
            component_limits.append(plugin.minimum_history(dict(component.get("parameters") or {})))
        return max(component_limits or [self.metadata.minimum_history, 35])

    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> StrategySignal:
        if not bars:
            return hold_strategy_signal(symbol, self.name, reason="insufficient_history", entry_price_ref=None)
        components = self._components(parameters)
        weighted_signals: list[WeightedSignal] = []
        for component in components:
            strategy_type = str(component.get("strategy_type") or "")
            plugin = self._COMPONENTS.get(strategy_type)
            if plugin is None:
                continue
            signal = StrategySignal.coerce(plugin.evaluate(symbol, bars, dict(component.get("parameters") or {}))).to_legacy()
            weighted_signals.append(
                WeightedSignal(
                    source=strategy_type,
                    signal=str(signal.get("signal") or "hold"),
                    strength=str(signal.get("strength") or "weak"),
                    weight=max(float(component.get("weight", 1) or 0), 0.0),
                    confidence=SignalFusionService.confidence_for(signal),
                    reason=str(signal.get("trigger_reason") or ""),
                    payload=signal,
                )
            )

        latest_close = round(float(bars[-1].close_price), 2)
        fusion = self.fusion_service.fuse(
            weighted_signals,
            min_confidence=clamp_fraction(parameters.get("min_confidence", 0.55), default=0.55),
            conflict_hold_threshold=clamp_fraction(parameters.get("conflict_hold_threshold", 0.2), default=0.2),
        )
        stop_loss_price, take_profit_price = risk_prices(latest_close, str(fusion["signal"]))
        return signal_from_payload({
            "symbol": symbol,
            "strategy": self.name,
            "entry_price_ref": latest_close,
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "position_pct": clamp_fraction(parameters.get("position_pct", 0.1), default=0.1) if fusion["signal"] == "buy" else 0.5 if fusion["signal"] == "reduce" else 1.0 if fusion["signal"] == "sell" else 0.0,
            "market_regime": "bullish" if fusion["signal"] == "buy" else "bearish" if fusion["signal"] in {"sell", "reduce"} else "neutral",
            "requires_recommendation_confirmation": fusion["signal"] == "buy",
            "filter_passed": True,
            "filter_reasons": [],
            **fusion,
        })

    @staticmethod
    def _components(parameters: dict[str, Any]) -> list[dict[str, Any]]:
        components = parameters.get("components")
        if isinstance(components, list) and components:
            return [component for component in components if isinstance(component, dict)]
        return [
            {"strategy_type": "rsi_reversal", "weight": 1, "parameters": {"rsi_period": 14, "oversold": 30, "overbought": 70, "position_pct": 0.1}},
            {"strategy_type": "bollinger_band", "weight": 1, "parameters": {"boll_period": 20, "stddev_multiplier": 2, "position_pct": 0.1}},
        ]
