from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FactorName = Literal["bias", "cci", "bbi", "wr"]


class SmartSelectionConfigRead(BaseModel):
    id: int
    tenant_id: str
    enabled: bool
    schedule_time: str
    config_payload: dict = Field(default_factory=dict)
    updated_at: str


class SmartSelectionConfigUpdate(BaseModel):
    enabled: bool | None = None
    config_payload: dict | None = None


class SmartSelectionItemRead(BaseModel):
    symbol: str
    code: str
    name: str
    score: float
    enhanced_score: float | None = None
    score_enhancement: dict = Field(default_factory=dict)
    price: float | None = None
    change_pct: float | None = None
    target_price: float | None = None
    stop_loss_price: float | None = None
    tags: list[str] = Field(default_factory=list)
    reason: str
    dimension_scores: dict = Field(default_factory=dict)
    raw_detail: dict = Field(default_factory=dict)


class SmartSelectionRunRead(BaseModel):
    id: int
    task_id: str | None = None
    status: Literal["queued", "running", "succeeded", "failed"]
    triggered_by: str
    candidate_pool_size: int
    recommendation_count: int
    summary: str | None = None
    report_body: str | None = None
    error_message: str | None = None
    progress_step: int = 0
    progress_total: int = 0
    progress_label: str | None = None
    generated_at: str | None = None
    started_at: str
    finished_at: str | None = None
    fund_flow_stats: dict = Field(default_factory=dict)


class SmartSelectionLatestRead(BaseModel):
    snapshot: SmartSelectionRunRead | None = None
    items: list[SmartSelectionItemRead] = Field(default_factory=list)
    latest_task: SmartSelectionRunRead | None = None


class SmartSelectionHistoryRead(BaseModel):
    runs: list[SmartSelectionRunRead] = Field(default_factory=list)


class SmartSelectionRunDispatchRead(BaseModel):
    status: Literal["queued"]
    run_id: int
    task_id: str


class SmartSelectionEvaluationRead(BaseModel):
    run_id: int
    status: str
    recommendation_count: int
    horizons: list[str]
    summary: dict = Field(default_factory=dict)
    items: list[dict] = Field(default_factory=list)


class SmartSelectionFactorRankRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    factor: FactorName = "bbi"
    source: str = "baostock"
    adjustflag: str = "2"
    limit: int = Field(default=120, ge=1, le=5000)


class SmartSelectionFactorRankItemRead(BaseModel):
    symbol: str
    factor: FactorName
    value: float | None = None
    rank: int | None = None
    missing_reason: str | None = None


class SmartSelectionFactorRankRead(BaseModel):
    factor: FactorName
    source: str
    adjustflag: str
    items: list[SmartSelectionFactorRankItemRead] = Field(default_factory=list)
