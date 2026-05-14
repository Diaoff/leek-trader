from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.quant.simulator import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_DRAWDOWN_PENALTY_COEF,
    DEFAULT_INITIAL_CASH,
    DEFAULT_MA_LONG_WINDOW,
    DEFAULT_MA_SHORT_WINDOW,
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_REWARD_MODE,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TURNOVER_PENALTY_COEF,
)


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


class IntradayBarRead(BaseModel):
    symbol: str
    bar_time: str
    interval: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    turnover: float = 0.0


class IntradayBarsRead(BaseModel):
    symbol: str
    source: str
    interval: str
    bars: list[IntradayBarRead]


class ProviderCapabilityRead(BaseModel):
    name: Literal["quote", "daily_bar", "intraday_bar", "fundamental", "concept", "fund_flow", "index", "fund", "bond"]
    supported: bool
    fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProviderProfileRead(BaseModel):
    name: str
    label: str
    capabilities: list[ProviderCapabilityRead]
    requires_login: bool = False
    supports_adjustment: bool = False
    stable_for_backtest: bool = False
    rate_limit_note: str | None = None
    failure_modes: list[str] = Field(default_factory=list)


class ProviderCapabilityMatrixRead(BaseModel):
    status: Literal["ready"]
    providers: list[ProviderProfileRead]


class ResearchStatusRead(BaseModel):
    code: Literal["ok", "empty_response", "network_failure", "schema_change", "rate_limit", "dependency_error"]
    notes: str | None = None


class StockFundFlowRead(BaseModel):
    source: str
    symbol: str
    trade_date: str | None = None
    main_net_inflow: float | None = None
    super_large_net_inflow: float | None = None
    large_net_inflow: float | None = None
    medium_net_inflow: float | None = None
    small_net_inflow: float | None = None
    main_net_ratio: float | None = None
    status: ResearchStatusRead


class ResearchNorthboundSummaryRead(BaseModel):
    source: str
    trade_date: str | None = None
    net_inflow: float | None = None
    unit: str = "CNY"
    status: ResearchStatusRead


class DragonTigerSeatRead(BaseModel):
    seat_name: str
    role: Literal["buy", "sell", "net"]
    amount: float | None = None
    net_amount: float | None = None
    tag: str | None = None


class DragonTigerStockRead(BaseModel):
    source: str
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
    seats: list[DragonTigerSeatRead] = Field(default_factory=list)
    status: ResearchStatusRead


class DragonTigerListRead(BaseModel):
    source: str
    trade_date: str | None = None
    symbol: str | None = None
    items: list[DragonTigerStockRead] = Field(default_factory=list)


class MarketDataQualityRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    source: str = "baostock"
    adjustflag: str = "2"


class MarketDataQualitySymbolReportRead(BaseModel):
    symbol: str
    rows: int
    first_trade_date: str | None = None
    last_trade_date: str | None = None
    suspended_rows: int
    st_rows: int
    null_counts: dict[str, int]
    calendar_gap_days: list[str]


class MarketDataQualityRead(BaseModel):
    status: str
    source: str
    adjustflag: str
    symbols: list[str]
    start_date: str | None = None
    end_date: str | None = None
    total_rows: int
    field_count: int
    nullable_fields: list[str]
    symbol_reports: list[MarketDataQualitySymbolReportRead]


class MarketSourceHealthItemRead(BaseModel):
    source: str
    label: str
    status: Literal["healthy", "partial", "empty"]
    role: Literal["primary", "fallback", "unavailable"]
    symbol_count: int
    row_count: int
    first_trade_date: str | None = None
    last_trade_date: str | None = None
    missing_symbols: list[str] = Field(default_factory=list)
    staleness_days: int | None = None
    health_level: Literal["healthy", "degraded", "down"]
    coverage_ratio: float
    empty_ratio: float
    field_missing_ratio: float
    freshness_score: float
    last_success_at: str | None = None
    last_failure_at: str | None = None
    recent_failure_count: int = 0
    recent_empty_count: int = 0
    avg_latency_ms: float | None = None
    runtime_health_level: Literal["healthy", "degraded", "down", "unknown"] = "unknown"
    notes: list[str] = Field(default_factory=list)


class MarketSourceHealthRead(BaseModel):
    status: Literal["healthy", "degraded", "empty"]
    symbols: list[str]
    start_date: str | None = None
    end_date: str | None = None
    adjustflag: str
    primary_source: str | None = None
    fallback_sources: list[str]
    failover_policy: dict[str, Any]
    sources: list[MarketSourceHealthItemRead]


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
    initial_cash: float = Field(default=DEFAULT_INITIAL_CASH, gt=0)
    commission_rate: float = Field(default=DEFAULT_COMMISSION_RATE, ge=0)
    slippage_rate: float = Field(default=DEFAULT_SLIPPAGE_RATE, ge=0)
    reward_mode: Literal["net_worth_change", "excess_return", "drawdown_penalty", "risk_adjusted_excess_return"] = DEFAULT_REWARD_MODE
    max_position_pct: float = Field(default=DEFAULT_MAX_POSITION_PCT, ge=0, le=1)
    ma_short_window: int = Field(default=DEFAULT_MA_SHORT_WINDOW, ge=1)
    ma_long_window: int = Field(default=DEFAULT_MA_LONG_WINDOW, ge=1)
    drawdown_penalty_coef: float = Field(default=DEFAULT_DRAWDOWN_PENALTY_COEF, ge=0, le=1)
    turnover_penalty_coef: float = Field(default=DEFAULT_TURNOVER_PENALTY_COEF, ge=0, le=1)
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


class RLTrainingScopeOptionRead(BaseModel):
    key: str
    label: str
    description: str


class RLTrainingScopeOptionsRead(BaseModel):
    scopes: list[RLTrainingScopeOptionRead]


class RLTrainingSymbolRead(BaseModel):
    symbol: str
    name: str | None = None
    source: str


RLTrainingScopeLiteral = Literal["watchlist", "special_attention", "smart_selection", "manual"]


class RLTrainingResolveRequest(BaseModel):
    scope: RLTrainingScopeLiteral = "watchlist"
    scopes: list[RLTrainingScopeLiteral] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=300)

    @field_validator("limit", mode="before")
    @classmethod
    def _default_limit(cls, value: Any) -> int:
        if value in (None, ""):
            return 50
        return value


class RLTrainingResolveRead(BaseModel):
    scope: str
    count: int
    symbols: list[RLTrainingSymbolRead]


class RLTrainingRequest(RLTrainingResolveRequest):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str = Field(default="RL 日线模型", min_length=1)
    algorithm: Literal["ppo_trading"] = "ppo_trading"
    start_date: date | None = None
    end_date: date | None = None
    source: str = "baostock"
    adjustflag: str = "2"
    exclude_suspended: bool = True
    total_timesteps: int = Field(default=100000, ge=1000, le=2000000)
    train_split_pct: float = Field(default=0.8, ge=0.5, le=0.95)
    ppo_n_steps: int = Field(default=512, ge=64, le=8192)
    ppo_batch_size: int = Field(default=64, ge=16, le=2048)
    ppo_learning_rate: float = Field(default=0.00031, gt=0, le=0.01)
    initial_cash: float = Field(default=DEFAULT_INITIAL_CASH, gt=0)
    commission_rate: float = Field(default=DEFAULT_COMMISSION_RATE, ge=0)
    slippage_rate: float = Field(default=DEFAULT_SLIPPAGE_RATE, ge=0)
    reward_mode: Literal["net_worth_change", "excess_return", "drawdown_penalty", "risk_adjusted_excess_return"] = DEFAULT_REWARD_MODE
    max_position_pct: float = Field(default=DEFAULT_MAX_POSITION_PCT, ge=0, le=1)
    ma_short_window: int = Field(default=DEFAULT_MA_SHORT_WINDOW, ge=1)
    ma_long_window: int = Field(default=DEFAULT_MA_LONG_WINDOW, ge=1)
    drawdown_penalty_coef: float = Field(default=DEFAULT_DRAWDOWN_PENALTY_COEF, ge=0, le=1)
    turnover_penalty_coef: float = Field(default=DEFAULT_TURNOVER_PENALTY_COEF, ge=0, le=1)
    min_validation_bars: int = Field(default=5, ge=1, le=252)


class RLModelStatusUpdateRequest(BaseModel):
    status: Literal["draft", "validated", "active", "retired"]


class RLModelRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    name: str
    status: str
    algorithm: str
    created_at: str
    updated_at: str
    scope: str
    symbols: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    training: dict[str, Any] = Field(default_factory=dict)
    splits: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    evaluations: list[dict[str, Any]] = Field(default_factory=list)
    dataset_manifest: dict[str, Any] = Field(default_factory=dict)


class RLModelListRead(BaseModel):
    models: list[RLModelRead] = Field(default_factory=list)


class RLModelCompareItemRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    name: str
    status: str
    algorithm: str
    scope: str
    symbol_count: int = 0
    start_date: str | None = None
    end_date: str | None = None
    avg_total_return_pct: float | None = None
    avg_max_drawdown_pct: float | None = None
    avg_excess_return_pct: float | None = None
    trade_count: int | None = None
    validation_passed: bool = False
    blockers: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class RLModelCompareRead(BaseModel):
    models: list[RLModelCompareItemRead] = Field(default_factory=list)


class RLModelDeleteRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    model_id: str


class RLTrainingJobRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    progress_step: int = 0
    progress_total: int = 1
    progress_pct: float = 0.0
    progress_label: str | None = None
    progress_details: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    model_id: str | None = None
    model: RLModelRead | None = None
    error: str | None = None


class SectorMomentumRead(BaseModel):
    sector: str
    rank: int
    avg_change_pct: float
    positive_ratio: float
    candidate_count: int
    leading_symbol: str | None = None
    leading_name: str | None = None
    momentum_score: float
