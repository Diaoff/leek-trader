from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class MarketQuoteRead(BaseModel):
    symbol: str
    code: str
    name: str
    price: float | None = None
    change_percent: float | None = None
    volume: float = 0.0
    sector: str | None = None


class MarketLimitStatsRead(BaseModel):
    total: int
    sample: list[MarketQuoteRead]
    source: str


class NorthboundSummaryRead(BaseModel):
    net_inflow: float | None = None
    unit: str = "CNY"
    source: str


class MarketSentimentRead(BaseModel):
    label: Literal["strong", "range", "weak"]
    title: str
    score: float
    selection_mode: Literal["momentum", "balanced", "defensive"]
    advancing_count: int
    declining_count: int
    flat_count: int
    limit_up_count: int
    limit_down_count: int
    northbound_net_inflow: float | None = None
    summary: str


class MarketBreadthBucketRead(BaseModel):
    key: str
    label: str
    count: int
    tone: Literal["rise", "fall"]


class MarketBreadthDistributionRead(BaseModel):
    advancing_count: int
    flat_count: int
    declining_count: int
    buckets: list[MarketBreadthBucketRead] = Field(default_factory=list)
    source: str


class MarketTurnoverSummaryRead(BaseModel):
    today_amount: float | None = None
    previous_day_amount: float | None = None
    delta_amount: float | None = None
    estimated_full_day_amount: float | None = None
    unit: str = "CNY"
    source: str


class MarketFundFlowItemRead(BaseModel):
    name: str
    net_inflow: float
    rank: int


class MarketRegionFundFlowItemRead(MarketFundFlowItemRead):
    longitude: float | None = None
    latitude: float | None = None


class MarketFundFlowRead(BaseModel):
    source: str
    regions: list[MarketRegionFundFlowItemRead] = Field(default_factory=list)
    concept_top: list[MarketFundFlowItemRead] = Field(default_factory=list)
    concept_bottom: list[MarketFundFlowItemRead] = Field(default_factory=list)
    industry_top: list[MarketFundFlowItemRead] = Field(default_factory=list)


class DailyBarRead(BaseModel):
    symbol: str
    trade_date: str
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


class DailyBarsRead(BaseModel):
    symbol: str
    source: str
    bars: list[DailyBarRead]


class BaoStockHistorySyncRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    start_date: date
    end_date: date
    adjustflag: str = "2"
    incremental: bool = False


class BaoStockHistorySyncFailureRead(BaseModel):
    symbol: str
    reason: str


class BaoStockHistorySyncRangeRead(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    skipped: bool = False
    reason: str | None = None


class BaoStockHistorySyncResultRead(BaseModel):
    status: str
    source: str
    adjustflag: str
    start_date: str
    end_date: str
    requested_symbols: list[str]
    incremental: bool
    resolved_ranges: list[BaoStockHistorySyncRangeRead]
    succeeded_symbols: list[str]
    success_count: int
    failure_count: int
    failures: list[BaoStockHistorySyncFailureRead]
    bars_upserted: int


class BaoStockHistorySyncTaskRead(BaseModel):
    task_id: str
    status: str


class RLDatasetRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    source: str = "baostock"
    adjustflag: str = "2"
    exclude_suspended: bool = True


class RLDatasetRead(BaseModel):
    status: str
    source: str
    adjustflag: str
    symbols: list[str]
    start_date: str | None = None
    end_date: str | None = None
    count: int
    fields: list[str]
    manifest: dict[str, Any]
    records: list[dict[str, Any]]


class RLDatasetSplitRequest(RLDatasetRequest):
    split_date: date
    gap_days: int = Field(default=0, ge=0)


class RLDatasetSplitRead(BaseModel):
    schema_version: str
    source: str
    adjustflag: str
    symbols: list[str]
    train: RLDatasetRead
    test: RLDatasetRead
    split_date: str
    gap_days: int
    feature_groups: dict[str, list[str]]
    manifest: dict[str, Any]
    leakage_checks: dict[str, Any]


class RLDatasetQualitySymbolReportRead(BaseModel):
    symbol: str
    rows: int
    first_trade_date: str | None = None
    last_trade_date: str | None = None
    suspended_rows: int
    st_rows: int
    null_counts: dict[str, int]
    calendar_gap_days: list[str]


class RLDatasetQualityRead(BaseModel):
    status: str
    source: str
    adjustflag: str
    symbols: list[str]
    start_date: str | None = None
    end_date: str | None = None
    total_rows: int
    field_count: int
    nullable_fields: list[str]
    symbol_reports: list[RLDatasetQualitySymbolReportRead]


class RLDatasetFeatureMetadataRead(BaseModel):
    schema_version: str
    fields: list[str]
    nullable_fields: list[str]
    feature_groups: dict[str, list[str]]
    descriptions: dict[str, str]
    normalization_hints: dict[str, str]


class RLEpisodeSimulateRequest(RLDatasetRequest):
    policy: Literal["buy_and_hold", "moving_average", "cash", "action_replay"] = "buy_and_hold"
    initial_cash: float = Field(default=100000.0, gt=0)
    commission_rate: float = Field(default=0.0003, ge=0)
    slippage_rate: float = Field(default=0.0002, ge=0)
    reward_mode: Literal["net_worth_change", "excess_return", "drawdown_penalty"] = "net_worth_change"
    max_position_pct: float = Field(default=1.0, ge=0, le=1)
    ma_short_window: int = Field(default=5, ge=1)
    ma_long_window: int = Field(default=20, ge=1)
    action_sequence: list[Any] = Field(default_factory=list)
    action_encoding: Literal["legacy_zero_based", "rl_stock_one_based"] = "legacy_zero_based"


class RLEpisodeStepRead(BaseModel):
    step: int
    symbol: str
    trade_date: str
    close_price: float
    action_type: str
    target_position_pct: float
    shares: int
    cash: float
    position_value: float
    net_worth: float
    reward: float
    benchmark_return: float
    drawdown_pct: float
    fee: float
    observation: dict[str, Any]


class RLEpisodeSimulationRead(BaseModel):
    status: str
    policy: str
    reward_mode: str
    initial_cash: float
    final_net_worth: float
    total_return_pct: float
    max_drawdown_pct: float
    total_reward: float
    total_fees: float
    feature_groups: dict[str, list[str]]
    summary: dict[str, Any]
    steps: list[RLEpisodeStepRead]
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    positions: list[dict[str, Any]] = Field(default_factory=list)
    rewards: list[dict[str, Any]] = Field(default_factory=list)


class RLStrategyPreviewRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    source: str = "baostock"
    adjustflag: str = "2"
    exclude_suspended: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class RLStrategyPreviewRead(BaseModel):
    status: str
    symbol: str
    signal: dict[str, Any]
    trajectory: RLEpisodeSimulationRead


class RLBatchEvaluationRequest(RLEpisodeSimulateRequest):
    symbols: list[str] = Field(..., min_length=1)


class RLBatchEvaluationTaskRead(BaseModel):
    task_id: str
    status: str


class RLBatchEvaluationRead(BaseModel):
    status: str
    success_count: int
    failure_count: int
    failures: list[dict[str, Any]]
    results: list[dict[str, Any]]
    ranking: list[dict[str, Any]]


class SectorMomentumRead(BaseModel):
    sector: str
    rank: int
    avg_change_pct: float
    positive_ratio: float
    candidate_count: int
    leading_symbol: str | None = None
    leading_name: str | None = None
    momentum_score: float


class MarketOverviewRead(BaseModel):
    generated_at: str
    indices: list[MarketQuoteRead]
    top_gainers: list[MarketQuoteRead]
    top_losers: list[MarketQuoteRead]
    limit_up: MarketLimitStatsRead
    limit_down: MarketLimitStatsRead
    northbound: NorthboundSummaryRead
    hot_stocks: list[MarketQuoteRead]
    market_sentiment: MarketSentimentRead | None = None
    breadth_distribution: MarketBreadthDistributionRead | None = None
    turnover_summary: MarketTurnoverSummaryRead | None = None
    sector_momentum_top: list[SectorMomentumRead] = Field(default_factory=list)
    fund_flow: MarketFundFlowRead | None = None
