import json
from datetime import UTC, datetime
from typing import Any, Iterator

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.config import DEFAULT_AI_PROMPT_CONFIG, INVESTOR_SYSTEM_PROMPT, STOCK_ANALYSIS_SYSTEM_PROMPT
from app.ai.core_analyzer import build_stock_analysis_prompt
from app.ai.data_loader import AiDataLoader
from app.ai.utils import extract_completion_text, extract_stream_text
from app.market.security_catalog import find_security_by_symbol
from app.market.symbols import normalize_a_share_symbol
from app.models.ai_config import AiConfig
from app.schemas.ai import (
    AiChatMessage,
    AiConfigRead,
    AiConfigUpdate,
    AiSecurityRead,
    AiStockAnalysisResponse,
)


class AiAnalysisService:
    model_request_timeout = DEFAULT_AI_PROMPT_CONFIG.model_request_timeout
    investor_system_prompt = INVESTOR_SYSTEM_PROMPT
    stock_analysis_system_prompt = STOCK_ANALYSIS_SYSTEM_PROMPT

    def __init__(self) -> None:
        self.data_loader = AiDataLoader()

    def get_config(self, db: Session, tenant_id: str) -> AiConfigRead:
        config = self._get_or_create_config(db, tenant_id)
        return self._to_config_read(config)

    def update_config(self, db: Session, tenant_id: str, payload: AiConfigUpdate) -> AiConfigRead:
        config = self._get_or_create_config(db, tenant_id)
        config.base_url = payload.base_url.strip()
        config.api_key = payload.api_key.strip()
        config.model = payload.model.strip()
        db.add(config)
        db.commit()
        db.refresh(config)
        return self._to_config_read(config)

    def chat(self, db: Session, tenant_id: str, messages: list[AiChatMessage]) -> tuple[str, str]:
        config = self._require_complete_config(db, tenant_id)
        payload = self._build_chat_payload(messages)
        content = self._request_completion(config, payload)
        return content, config.model

    def stream_chat(self, db: Session, tenant_id: str, messages: list[AiChatMessage]) -> tuple[Iterator[str], str]:
        config = self._require_complete_config(db, tenant_id)
        payload = self._build_chat_payload(messages)
        return self._stream_completion(config, payload), config.model

    def analyze_stock(
        self,
        db: Session,
        tenant_id: str,
        symbol: str,
        note: str | None = None,
    ) -> AiStockAnalysisResponse:
        config, response_stub, payload = self._prepare_stock_analysis(db, tenant_id, symbol, note)
        content = self._request_completion(config, payload)
        response_stub.content = content
        return response_stub

    def stream_analyze_stock(
        self,
        db: Session,
        tenant_id: str,
        symbol: str,
        note: str | None = None,
    ) -> tuple[AiStockAnalysisResponse, Iterator[str], str]:
        config, response_stub, payload = self._prepare_stock_analysis(db, tenant_id, symbol, note)
        return response_stub, self._stream_completion(config, payload), config.model

    def _get_or_create_config(self, db: Session, tenant_id: str) -> AiConfig:
        config = db.scalar(select(AiConfig).where(AiConfig.tenant_id == tenant_id))
        if config is not None:
            return config

        config = AiConfig(tenant_id=tenant_id)
        db.add(config)
        db.commit()
        db.refresh(config)
        return config

    def _require_complete_config(self, db: Session, tenant_id: str) -> AiConfig:
        config = self._get_or_create_config(db, tenant_id)
        if config.base_url and config.api_key and config.model:
            return config
        raise HTTPException(status_code=400, detail="AI 配置不完整，请先填写 Base URL、API Key 和 Model")

    @staticmethod
    def _to_config_read(config: AiConfig) -> AiConfigRead:
        return AiConfigRead(
            base_url=config.base_url or "",
            api_key=config.api_key or "",
            model=config.model or "",
            configured=bool(config.base_url and config.api_key and config.model),
        )

    def _build_chat_payload(self, messages: list[AiChatMessage]) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.investor_system_prompt},
            *[message.model_dump() for message in messages],
        ]

    def _request_completion(self, config: AiConfig, messages: list[dict[str, str]]) -> str:
        try:
            with httpx.Client(timeout=self.model_request_timeout) as client:
                response = client.post(
                    self._build_chat_url(config.base_url),
                    headers={
                        "Authorization": f"Bearer {config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": config.model,
                        "messages": messages,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400] if exc.response is not None else str(exc)
            raise HTTPException(status_code=502, detail=f"AI 服务请求失败: {detail}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"AI 服务连接失败: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="AI 服务返回了无效响应") from exc

        content = extract_completion_text(payload)
        if not content:
            raise HTTPException(status_code=502, detail="AI 服务没有返回有效内容")
        return content

    def _stream_completion(self, config: AiConfig, messages: list[dict[str, str]]) -> Iterator[str]:
        try:
            with httpx.Client(timeout=self.model_request_timeout) as client:
                with client.stream(
                    "POST",
                    self._build_chat_url(config.base_url),
                    headers={
                        "Authorization": f"Bearer {config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": config.model,
                        "messages": messages,
                        "stream": True,
                    },
                ) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()

                    if "text/event-stream" not in content_type:
                        payload = response.json()
                        content = extract_completion_text(payload)
                        if content:
                            yield content
                        return

                    for raw_line in response.iter_lines():
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue

                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue

                        try:
                            payload = json.loads(data)
                        except ValueError:
                            continue

                        chunk = extract_stream_text(payload)
                        if chunk:
                            yield chunk
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400] if exc.response is not None else str(exc)
            raise HTTPException(status_code=502, detail=f"AI 流式请求失败: {detail}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"AI 流式连接失败: {exc}") from exc

    @staticmethod
    def _build_chat_url(base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    def _prepare_stock_analysis(
        self,
        db: Session,
        tenant_id: str,
        symbol: str,
        note: str | None = None,
    ) -> tuple[AiConfig, AiStockAnalysisResponse, list[dict[str, str]]]:
        config = self._require_complete_config(db, tenant_id)
        normalized_symbol = normalize_a_share_symbol(symbol)
        security = find_security_by_symbol(normalized_symbol)
        if security is None:
            raise HTTPException(status_code=404, detail="未找到对应证券")

        try:
            stock_context = self.data_loader.load_stock_context(normalized_symbol, security_name=str(security["name"]))
        except TypeError as exc:
            if "security_name" not in str(exc):
                raise
            stock_context = self.data_loader.load_stock_context(normalized_symbol)
        prompt = build_stock_analysis_prompt(security, stock_context, note)

        response_stub = AiStockAnalysisResponse(
            symbol=normalized_symbol,
            security=AiSecurityRead(
                symbol=str(security["symbol"]),
                code=str(security["code"]),
                name=str(security["name"]),
                market=str(security["market"]),
                tags=[str(tag) for tag in security.get("tags", [])],
            ),
            content="",
            generated_at=datetime.now(UTC),
            latest_price=stock_context.quote.price if stock_context.quote else None,
            change_percent=stock_context.quote.change_percent if stock_context.quote else None,
        )
        payload = [
            {"role": "system", "content": self.stock_analysis_system_prompt},
            {"role": "user", "content": prompt},
        ]
        return config, response_stub, payload
