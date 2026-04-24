from __future__ import annotations

from typing import Literal

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


class MarketRecommendationRead(BaseModel):
    symbol: str
    code: str
    name: str
    type: Literal["stock", "etf"] = "stock"
    risk: Literal["low", "medium", "high"]
    reason: str
    price: float | None = None
    change_pct: float | None = None
    source: Literal["rule_engine", "fallback_etf", "research_snapshot"] = "research_snapshot"
    score: float | None = None
    strategy: str | None = None
    layer: Literal["oversold", "support", "pullback"] | None = None
    sector: str | None = None
    sector_rank: int | None = None
    reasons: list[str] = Field(default_factory=list)
    support_type: str | None = None
    support_price: float | None = None
    support_distance_pct: float | None = None
    atr_stop_loss: float | None = None
    run_id: int | None = None
    previous_recommendation_price: float | None = None
    previous_recommendation_at: str | None = None


class MarketResearchRunRead(BaseModel):
    id: int
    task_id: str | None = None
    status: Literal["queued", "running", "succeeded", "failed"]
    triggered_by: str
    candidate_pool_size: int
    recommendation_count: int
    northbound_net_inflow: float | None = None
    summary: str | None = None
    report_summary: str | None = None
    error_message: str | None = None
    generated_at: str | None = None
    started_at: str
    finished_at: str | None = None
    market_sentiment: MarketSentimentRead | None = None
    sector_momentum_top: list[SectorMomentumRead] = Field(default_factory=list)


class MarketResearchLatestRead(BaseModel):
    snapshot: MarketResearchRunRead | None = None
    items: list[MarketRecommendationRead] = Field(default_factory=list)
    latest_task: MarketResearchRunRead | None = None


class MarketResearchRunDispatchRead(BaseModel):
    status: Literal["queued"]
    run_id: int
    task_id: str


class MarketResearchHistoryRead(BaseModel):
    runs: list[MarketResearchRunRead] = Field(default_factory=list)
