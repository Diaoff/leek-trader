from abc import ABC, abstractmethod


class StrategyPlugin(ABC):
    name: str

    @abstractmethod
    def evaluate(self, symbol: str, prices: list[float], parameters: dict) -> dict[str, object]:
        raise NotImplementedError
