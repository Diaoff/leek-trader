from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AiConfigRead(BaseModel):
    base_url: str
    api_key: str
    model: str
    configured: bool


class AiConfigUpdate(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class AiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class AiChatRequest(BaseModel):
    messages: list[AiChatMessage] = Field(min_length=1, max_length=30)


class AiChatResponse(BaseModel):
    content: str
    model: str


class AiStockAnalysisRequest(BaseModel):
    symbol: str
    note: str | None = Field(default=None, max_length=255)


class AiSecurityRead(BaseModel):
    symbol: str
    code: str
    name: str
    market: str
    tags: list[str]


class AiStockAnalysisResponse(BaseModel):
    symbol: str
    security: AiSecurityRead
    content: str
    generated_at: datetime
    latest_price: float | None = None
    change_percent: float | None = None

    model_config = ConfigDict(from_attributes=True)
