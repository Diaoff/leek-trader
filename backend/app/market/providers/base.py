from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


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


@dataclass(slots=True)
class DailyBarSnapshot:
    symbol: str
    trade_date: date
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    volume: float
    turnover: float = 0.0
    amplitude_pct: float | None = None
    change_pct: float | None = None
    turnover_rate: float | None = None


class PriceHistoryProvider(ABC):
    name: str

    @abstractmethod
    def fetch_daily_bars(self, symbol: str, limit: int = 60) -> list[DailyBarSnapshot]:
        raise NotImplementedError


@dataclass(slots=True)
class MarketSymbolSnapshot:
    symbol: str
    code: str
    name: str
    price: float | None
    change_percent: float | None
    volume: float = 0.0
    sector: str | None = None


@dataclass(slots=True)
class MarketBreadthBucketSnapshot:
    key: str
    label: str
    count: int
    tone: Literal["rise", "fall"]


@dataclass(slots=True)
class MarketBreadthDistributionSnapshot:
    advancing_count: int = 0
    flat_count: int = 0
    declining_count: int = 0
    buckets: list[MarketBreadthBucketSnapshot] = field(default_factory=list)
    source: str = "none"


@dataclass(slots=True)
class MarketTurnoverSnapshot:
    today_amount: float | None = None
    previous_day_amount: float | None = None
    delta_amount: float | None = None
    estimated_full_day_amount: float | None = None
    source: str = "none"


@dataclass(slots=True)
class MarketFundFlowItemSnapshot:
    name: str
    net_inflow: float
    rank: int


@dataclass(slots=True)
class MarketRegionFundFlowItemSnapshot(MarketFundFlowItemSnapshot):
    longitude: float | None = None
    latitude: float | None = None


@dataclass(slots=True)
class MarketFundFlowSnapshot:
    source: str = "none"
    regions: list[MarketRegionFundFlowItemSnapshot] = field(default_factory=list)
    concept_top: list[MarketFundFlowItemSnapshot] = field(default_factory=list)
    concept_bottom: list[MarketFundFlowItemSnapshot] = field(default_factory=list)
    industry_top: list[MarketFundFlowItemSnapshot] = field(default_factory=list)


@dataclass(slots=True)
class MarketOverviewSnapshot:
    generated_at: datetime
    source: str
    indices: list[MarketSymbolSnapshot] = field(default_factory=list)
    top_gainers: list[MarketSymbolSnapshot] = field(default_factory=list)
    top_losers: list[MarketSymbolSnapshot] = field(default_factory=list)
    limit_up_total: int = 0
    limit_up_sample: list[MarketSymbolSnapshot] = field(default_factory=list)
    limit_down_total: int = 0
    limit_down_sample: list[MarketSymbolSnapshot] = field(default_factory=list)
    northbound_net_inflow: float | None = None
    hot_stocks: list[MarketSymbolSnapshot] = field(default_factory=list)
    breadth_distribution: MarketBreadthDistributionSnapshot | None = None
    turnover: MarketTurnoverSnapshot | None = None
    fund_flow: MarketFundFlowSnapshot | None = None


class MarketOverviewProvider(ABC):
    name: str

    @abstractmethod
    def fetch_overview(self) -> MarketOverviewSnapshot:
        raise NotImplementedError
