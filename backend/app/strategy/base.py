from abc import ABC, abstractmethod
from typing import Any

from app.market.providers.base import DailyBarSnapshot
from app.strategy.contracts import StrategySignal


class StrategyPlugin(ABC):
    name: str

    @abstractmethod
    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> dict[str, Any] | StrategySignal:
        raise NotImplementedError
