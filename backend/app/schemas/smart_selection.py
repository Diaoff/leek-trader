from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    generated_at: str | None = None
    started_at: str
    finished_at: str | None = None


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
