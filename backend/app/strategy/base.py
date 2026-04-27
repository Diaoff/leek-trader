from abc import ABC, abstractmethod

from app.market.providers.base import DailyBarSnapshot


class StrategyPlugin(ABC):
    name: str

    @abstractmethod
    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> dict[str, object]:
        raise NotImplementedError
