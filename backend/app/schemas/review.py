from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DailyReviewRead(BaseModel):
    id: int
    review_date: date | None
    symbol: str
    strategy_id: int | None = None
    strategy_name: str | None = None
    strategy_type: str
    headline: str
    highlights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    backtest_summary: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DailyReviewListRead(BaseModel):
    reviews: list[DailyReviewRead] = Field(default_factory=list)
