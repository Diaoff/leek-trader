from abc import ABC, abstractmethod
from typing import Any

from app.market.providers.base import DailyBarSnapshot
from app.strategy.contracts import StrategyContext, StrategyMetadata, StrategySignal


class StrategyPlugin(ABC):
    name: str
    metadata: StrategyMetadata

    @abstractmethod
    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> dict[str, Any] | StrategySignal:
        raise NotImplementedError

    def minimum_history(self, parameters: dict[str, Any]) -> int:
        return self.metadata.minimum_history

    def build_context(
        self,
        *,
        execution_mode: str,
        parameters: dict[str, Any],
        history_available: int,
        environment: str = "paper",
        available_cash: float | None = None,
        position_value: float | None = None,
        total_equity: float | None = None,
        position_symbols: tuple[str, ...] = (),
    ) -> StrategyContext:
        minimum_history = self.minimum_history(parameters)
        return StrategyContext(
            environment=environment,  # type: ignore[arg-type]
            execution_mode=execution_mode,
            available_cash=available_cash,
            position_value=position_value,
            total_equity=total_equity,
            position_symbols=position_symbols,
            paper_trading=environment == "paper",
            backtest=environment == "backtest",
            strategy_parameters=dict(parameters),
            minimum_history=minimum_history,
            history_ready=history_available >= minimum_history,
            history_available=history_available,
        )
