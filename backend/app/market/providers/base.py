from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


ProviderCapabilityName = Literal[
    "quote",
    "daily_bar",
    "intraday_bar",
    "fundamental",
    "concept",
    "fund_flow",
    "index",
    "fund",
    "bond",
]

ProviderFailureMode = Literal[
    "network_failure",
    "schema_change",
    "empty_response",
    "rate_limit",
    "dependency_error",
]


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    name: ProviderCapabilityName
    supported: bool
    fields: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    name: str
    label: str
    capabilities: tuple[ProviderCapability, ...]
    requires_login: bool = False
    supports_adjustment: bool = False
    stable_for_backtest: bool = False
    rate_limit_note: str | None = None
    failure_modes: tuple[str, ...] = ()


def capability(
    name: ProviderCapabilityName,
    *,
    supported: bool,
    fields: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> ProviderCapability:
    return ProviderCapability(name=name, supported=supported, fields=fields, notes=notes)


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
    preclose: float | None = None
    trade_status: int | None = None
    pe_ttm: float | None = None
    pb_mrq: float | None = None
    ps_ttm: float | None = None
    pcf_ncf_ttm: float | None = None
    is_st: bool | None = None


@dataclass(slots=True)
class IntradayBarSnapshot:
    symbol: str
    bar_time: datetime
    interval: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    turnover: float = 0.0


class PriceHistoryProvider(ABC):
    name: str

    @abstractmethod
    def fetch_daily_bars(self, symbol: str, limit: int = 60) -> list[DailyBarSnapshot]:
        raise NotImplementedError


class IntradayBarProvider(ABC):
    name: str

    @abstractmethod
    def fetch_intraday_bars(self, symbol: str, interval: str = "5m", limit: int = 120) -> list[IntradayBarSnapshot]:
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


@dataclass(slots=True)
class ResearchStatusSnapshot:
    code: Literal["ok", "empty_response", "network_failure", "schema_change", "rate_limit", "dependency_error"]
    notes: str | None = None


@dataclass(slots=True)
class StockFundFlowSnapshot:
    symbol: str
    trade_date: str | None
    main_net_inflow: float | None = None
    super_large_net_inflow: float | None = None
    large_net_inflow: float | None = None
    medium_net_inflow: float | None = None
    small_net_inflow: float | None = None
    main_net_ratio: float | None = None
    source: str = "none"
    status: ResearchStatusSnapshot = field(default_factory=lambda: ResearchStatusSnapshot(code="ok"))


@dataclass(slots=True)
class NorthboundSummarySnapshot:
    net_inflow: float | None = None
    trade_date: str | None = None
    unit: str = "CNY"
    source: str = "none"
    status: ResearchStatusSnapshot = field(default_factory=lambda: ResearchStatusSnapshot(code="ok"))


@dataclass(slots=True)
class DragonTigerSeatSnapshot:
    seat_name: str
    role: Literal["buy", "sell", "net"]
    amount: float | None = None
    net_amount: float | None = None
    tag: str | None = None


@dataclass(slots=True)
class DragonTigerStockSnapshot:
    symbol: str
    stock_name: str
    trade_date: str
    reason: str | None = None
    close_price: float | None = None
    change_percent: float | None = None
    turnover_rate: float | None = None
    buy_amount: float | None = None
    sell_amount: float | None = None
    net_amount: float | None = None
    seats: list[DragonTigerSeatSnapshot] = field(default_factory=list)
    source: str = "none"
    status: ResearchStatusSnapshot = field(default_factory=lambda: ResearchStatusSnapshot(code="ok"))


class ResearchProvider(ABC):
    name: str

    @abstractmethod
    def fetch_stock_fund_flow(self, symbol: str) -> StockFundFlowSnapshot:
        raise NotImplementedError

    @abstractmethod
    def fetch_dragon_tiger(self, trade_date: str | None = None, symbol: str | None = None) -> list[DragonTigerStockSnapshot]:
        raise NotImplementedError
