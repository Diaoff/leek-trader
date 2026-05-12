from __future__ import annotations

from app.models.strategy import StrategyType
from app.strategy.base import StrategyPlugin
from app.strategy.strategies.macd import MacdStrategy
from app.strategy.strategies.bollinger_band import BollingerBandStrategy
from app.strategy.strategies.kdj_momentum import KdjMomentumStrategy
from app.strategy.strategies.moving_average import MovingAverageStrategy
from app.strategy.strategies.rsi_reversal import RsiReversalStrategy
from app.strategy.strategies.rl_trading import RLTradingStrategy
from app.strategy.strategies.signal_fusion import SignalFusionStrategy


class StrategyPluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, StrategyPlugin] = {
            StrategyType.MOVING_AVERAGE.value: MovingAverageStrategy(),
            StrategyType.MACD.value: MacdStrategy(),
            StrategyType.RL_TRADING.value: RLTradingStrategy(),
            StrategyType.RSI_REVERSAL.value: RsiReversalStrategy(),
            StrategyType.BOLLINGER_BAND.value: BollingerBandStrategy(),
            StrategyType.KDJ_MOMENTUM.value: KdjMomentumStrategy(),
            StrategyType.SIGNAL_FUSION.value: SignalFusionStrategy(),
        }

    @property
    def plugins(self) -> dict[str, StrategyPlugin]:
        return self._plugins

    def get(self, strategy_type: str) -> StrategyPlugin:
        plugin = self._plugins.get(strategy_type)
        if plugin is None:
            raise ValueError(f"unsupported strategy type: {strategy_type}")
        return plugin
