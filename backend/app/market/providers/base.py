from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class QuoteSnapshot:
    symbol: str
    price: float
    change_percent: float
    volume: float
    timestamp: datetime
    is_halted: bool = False
    market_cap: float | None = None
    ytd_change_percent: float | None = None


class QuoteProvider(ABC):
    name: str

    @abstractmethod
    def fetch_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        raise NotImplementedError
