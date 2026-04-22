from app.models.strategy import StrategyStatus, StrategyType
from app.schemas.strategy import StrategyRead
from app.strategy.base import StrategyPlugin
from app.strategy.strategies.macd import MacdStrategy
from app.strategy.strategies.moving_average import MovingAverageStrategy

DEFAULT_PRICE_SERIES = {
    "sh600519": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
    "sz000001": [12, 11.9, 11.8, 11.7, 11.6, 11.5, 11.4, 11.3, 11.2, 11.1, 11.0, 10.9, 10.8, 10.7, 10.6, 10.5, 10.4, 10.3, 10.2, 10.1],
}

STRATEGY_DEFINITIONS = [
    {
        "id": 1,
        "tenant_id": "local",
        "name": "双均线策略",
        "strategy_type": StrategyType.MOVING_AVERAGE.value,
        "status": StrategyStatus.ACTIVE.value,
        "parameters": {"short_window": 5, "long_window": 20},
        "symbol": "sh600519",
    },
    {
        "id": 2,
        "tenant_id": "local",
        "name": "MACD 策略",
        "strategy_type": StrategyType.MACD.value,
        "status": StrategyStatus.ACTIVE.value,
        "parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
        "symbol": "sz000001",
    },
]


class StrategyService:
    def __init__(self) -> None:
        self.plugins: dict[str, StrategyPlugin] = {
            StrategyType.MOVING_AVERAGE.value: MovingAverageStrategy(),
            StrategyType.MACD.value: MacdStrategy(),
        }

    def list_strategies(self) -> list[StrategyRead]:
        items: list[StrategyRead] = []
        for definition in STRATEGY_DEFINITIONS:
            signal = self._evaluate_definition(definition)
            items.append(
                StrategyRead(
                    id=definition["id"],
                    tenant_id=definition["tenant_id"],
                    name=definition["name"],
                    strategy_type=definition["strategy_type"],
                    status=definition["status"],
                    parameters=definition["parameters"],
                    latest_signal=signal["signal"],
                    signal_symbol=signal["symbol"],
                )
            )
        return items

    def _evaluate_definition(self, definition: dict) -> dict[str, object]:
        plugin = self.plugins[definition["strategy_type"]]
        prices = DEFAULT_PRICE_SERIES[definition["symbol"]]
        return plugin.evaluate(definition["symbol"], prices, definition["parameters"])
