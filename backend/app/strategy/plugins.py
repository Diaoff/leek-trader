from __future__ import annotations

from app.models.strategy import StrategyType
from app.strategy.base import StrategyPlugin
from app.strategy.strategies.macd import MacdStrategy
from app.strategy.strategies.moving_average import MovingAverageStrategy
from app.strategy.strategies.rl_trading import RLTradingStrategy


class StrategyPluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, StrategyPlugin] = {
            StrategyType.MOVING_AVERAGE.value: MovingAverageStrategy(),
            StrategyType.MACD.value: MacdStrategy(),
            StrategyType.RL_TRADING.value: RLTradingStrategy(),
        }

    @property
    def plugins(self) -> dict[str, StrategyPlugin]:
        return self._plugins

    def get(self, strategy_type: str) -> StrategyPlugin:
        plugin = self._plugins.get(strategy_type)
        if plugin is None:
            raise ValueError(f"unsupported strategy type: {strategy_type}")
        return plugin
