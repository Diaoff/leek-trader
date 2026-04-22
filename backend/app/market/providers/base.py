from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class QuoteSnapshot:
    symbol: str
    price: float
    change_percent: float
    volume: float
    timestamp: datetime
    is_halted: bool = False


class QuoteProvider(ABC):
    name: str

    @abstractmethod
    def fetch_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        raise NotImplementedError

    def build_placeholder_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        now = datetime.now(timezone.utc)
        return [
            QuoteSnapshot(
                symbol=symbol,
                price=10.0,
                change_percent=0.0,
                volume=0.0,
                timestamp=now,
                is_halted=False,
            )
            for symbol in symbols
        ]
