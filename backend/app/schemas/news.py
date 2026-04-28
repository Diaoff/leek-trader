from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

NewsSource = Literal["xuangubao", "jiuyangongshe", "xueqiu"]


class NewsItemRead(BaseModel):
    id: str
    source: NewsSource
    title: str
    summary: str = ""
    published_at: datetime | None = None
    author: str = ""
    url: str = ""
    symbol_keyword: str = ""

    model_config = ConfigDict(from_attributes=True)


class NewsFeedResponse(BaseModel):
    items: list[NewsItemRead]
    errors: list[str] = []


class NewsBriefResponse(BaseModel):
    market: list[NewsItemRead]
    discussions: list[NewsItemRead]
    xueqiu: list[NewsItemRead]
    errors: list[str] = []
