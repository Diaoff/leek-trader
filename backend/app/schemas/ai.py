from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AiProvider(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    DEEPSEEK = "deepseek"
    SILICONFLOW = "siliconflow"
    OLLAMA = "ollama"
    CUSTOM = "custom"


class AiAgentType(StrEnum):
    RESEARCH_AGENT = "research_agent"
    PARAMETER_ADVISOR = "parameter_advisor"
    RISK_EXPLAINER = "risk_explainer"


class AiConfigRead(BaseModel):
    provider: AiProvider
    base_url: str
    api_key: str
    model: str
    configured: bool
    provider_display_name: str | None = None
    provider_base_url_hint: str | None = None
    provider_api_key_required: bool = True
    provider_model_hint: str | None = None


class AiConfigUpdate(BaseModel):
    provider: AiProvider = AiProvider.OPENAI_COMPATIBLE
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


class AiAgentRunRequest(BaseModel):
    agent_type: AiAgentType
    context: dict[str, Any]
    symbol: str | None = None
    strategy_type: str | None = None
    result_ref: str | None = None
    strategy_run_id: int | None = None
    order_id: int | None = None
    correlation_id: str | None = None


class AiStructuredResult(BaseModel):
    parse_status: Literal["succeeded", "failed"]
    data: dict[str, Any] | None = None
    raw_content: str | None = None


class AiAgentRunResponse(BaseModel):
    agent_type: AiAgentType
    provider: AiProvider
    model: str
    content: str
    structured: AiStructuredResult
    warnings: list[str] = Field(default_factory=list)
    recoverable: bool = False


class AiParameterAdviceRequest(BaseModel):
    symbol: str
    strategy_type: str
    current_parameters: dict[str, Any]
    optimization_job_id: str | None = None
    backtest_job_id: str | None = None
    strategy_run_id: int | None = None
    order_id: int | None = None
    correlation_id: str | None = None


class AiParameterAdviceResponse(BaseModel):
    symbol: str
    strategy_type: str
    provider: AiProvider
    model: str
    content: str
    structured: AiStructuredResult
    warnings: list[str] = Field(default_factory=list)
    recoverable: bool = False


class AiProviderErrorRead(BaseModel):
    code: str
    message: str
    recoverable: bool = False
    provider: AiProvider | None = None
