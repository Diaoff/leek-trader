from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterator

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.agents import build_agent_messages, parse_structured_content
from app.ai.config import DEFAULT_AI_PROMPT_CONFIG, INVESTOR_SYSTEM_PROMPT, STOCK_ANALYSIS_SYSTEM_PROMPT
from app.ai.core_analyzer import build_stock_analysis_prompt
from app.ai.data_loader import AiDataLoader
from app.ai.providers import get_provider_profile
from app.ai.utils import extract_completion_text, extract_stream_text
from app.backtest.jobs import BacktestJobRegistry
from app.market.security_catalog import find_security_by_symbol
from app.market.symbols import normalize_a_share_symbol
from app.models.ai_config import AiConfig
from app.schemas.ai import (
    AiAgentRunRequest,
    AiAgentRunResponse,
    AiAgentType,
    AiChatMessage,
    AiConfigRead,
    AiConfigUpdate,
    AiParameterAdviceRequest,
    AiParameterAdviceResponse,
    AiProvider,
    AiSecurityRead,
    AiStockAnalysisResponse,
    AiStructuredResult,
)


class AiAnalysisService:
    model_request_timeout = DEFAULT_AI_PROMPT_CONFIG.model_request_timeout
    investor_system_prompt = INVESTOR_SYSTEM_PROMPT
    stock_analysis_system_prompt = STOCK_ANALYSIS_SYSTEM_PROMPT

    provider_error_codes = {
        "config": "config_incomplete",
        "timeout": "provider_timeout",
        "http": "provider_http_error",
        "bad_payload": "provider_bad_payload",
        "stream": "stream_interrupted",
        "context": "context_unavailable",
        "parse": "llm_parse_failed",
    }

    def __init__(self) -> None:
        self.data_loader = AiDataLoader()
        self.backtest_jobs = BacktestJobRegistry()
        self.optimization_jobs = BacktestJobRegistry(prefix="backtest-optimization", job_kind="optimization")
        self.portfolio_jobs = BacktestJobRegistry(prefix="portfolio-backtest", job_kind="portfolio")

    def get_config(self, db: Session, tenant_id: str, user_id: int | None = None) -> AiConfigRead:
        config = self._get_or_create_config(db, tenant_id, user_id)
        return self._to_config_read(config)

    def update_config(self, db: Session, tenant_id: str, payload: AiConfigUpdate, user_id: int | None = None) -> AiConfigRead:
        config = self._get_or_create_config(db, tenant_id, user_id)
        config.provider = payload.provider.value
        config.base_url = payload.base_url.strip()
        config.api_key = payload.api_key.strip()
        config.model = payload.model.strip()
        db.add(config)
        db.commit()
        db.refresh(config)
        return self._to_config_read(config)

    def chat(self, db: Session, tenant_id: str, messages: list[AiChatMessage], user_id: int | None = None) -> tuple[str, str]:
        config = self._require_complete_config(db, tenant_id, user_id)
        content = self._request_completion(config, self._build_chat_payload(messages))
        return content, config.model

    def stream_chat(self, db: Session, tenant_id: str, messages: list[AiChatMessage], user_id: int | None = None) -> tuple[Iterator[str], str]:
        config = self._require_complete_config(db, tenant_id, user_id)
        return self._stream_completion(config, self._build_chat_payload(messages)), config.model

    def analyze_stock(
        self,
        db: Session,
        tenant_id: str,
        symbol: str,
        note: str | None = None,
        user_id: int | None = None,
    ) -> AiStockAnalysisResponse:
        config, response_stub, payload = self._prepare_stock_analysis(db, tenant_id, symbol, note, user_id=user_id)
        response_stub.content = self._request_completion(config, payload)
        return response_stub

    def stream_analyze_stock(
        self,
        db: Session,
        tenant_id: str,
        symbol: str,
        note: str | None = None,
        user_id: int | None = None,
    ) -> tuple[AiStockAnalysisResponse, Iterator[str], str]:
        config, response_stub, payload = self._prepare_stock_analysis(db, tenant_id, symbol, note, user_id=user_id)
        return response_stub, self._stream_completion(config, payload), config.model

    def run_agent(
        self,
        db: Session,
        tenant_id: str,
        payload: AiAgentRunRequest,
        user_id: int | None = None,
    ) -> AiAgentRunResponse:
        config = self._require_complete_config(db, tenant_id, user_id)
        context = self._build_agent_context(db, payload, user_id)
        content = self._request_completion(config, build_agent_messages(payload, context))
        structured = parse_structured_content(content)
        warnings = list(context.get("warnings", []))
        if structured.parse_status == "failed":
            warnings.append("模型返回了非结构化内容，已保留原文供人工检查。")
        return AiAgentRunResponse(
            agent_type=payload.agent_type,
            provider=AiProvider(config.provider),
            model=config.model,
            content=content,
            structured=structured,
            warnings=warnings,
            recoverable=structured.parse_status == "failed",
        )

    def parameter_advice(
        self,
        db: Session,
        tenant_id: str,
        payload: AiParameterAdviceRequest,
        user_id: int | None = None,
    ) -> AiParameterAdviceResponse:
        config = self._get_or_create_config(db, tenant_id, user_id)
        context = self._build_parameter_advice_context(payload, user_id)
        agent_payload = AiAgentRunRequest(
            agent_type=AiAgentType.PARAMETER_ADVISOR,
            context=context,
            symbol=payload.symbol,
            strategy_type=payload.strategy_type,
            result_ref=payload.optimization_job_id or payload.backtest_job_id,
        )
        try:
            self._validate_provider_config(config)
            content = self._request_completion(config, build_agent_messages(agent_payload, context))
            structured = parse_structured_content(content)
            warnings = list(context.get("warnings", []))
            if structured.parse_status == "failed":
                warnings.append("模型未返回可解析 JSON，已保留原文。")
            return AiParameterAdviceResponse(
                symbol=payload.symbol,
                strategy_type=payload.strategy_type,
                provider=AiProvider(config.provider),
                model=config.model,
                content=content,
                structured=structured,
                warnings=warnings,
                recoverable=structured.parse_status == "failed",
            )
        except HTTPException as exc:
            detail = self._exception_detail(exc)
            error_code = self._exception_code(exc)
            structured = AiStructuredResult(parse_status="failed", raw_content=detail, data={"code": error_code} if error_code else None)
            warnings = list(context.get("warnings", []))
            if error_code:
                warnings.append(error_code)
            warnings.append("AI 调用失败，建议先检查 Provider 配置或运行参数扫描。")
            return AiParameterAdviceResponse(
                symbol=payload.symbol,
                strategy_type=payload.strategy_type,
                provider=AiProvider(config.provider),
                model=config.model,
                content=detail,
                structured=structured,
                warnings=warnings,
                recoverable=True,
            )

    def _get_or_create_config(self, db: Session, tenant_id: str, user_id: int | None = None) -> AiConfig:
        if user_id is None:
            config = db.scalar(select(AiConfig).where(AiConfig.tenant_id == tenant_id, AiConfig.user_id.is_(None)))
        else:
            config = db.scalar(select(AiConfig).where(AiConfig.user_id == user_id))
        if config is not None:
            return config

        config = AiConfig(tenant_id=tenant_id, user_id=user_id, provider="openai_compatible")
        db.add(config)
        db.commit()
        db.refresh(config)
        return config

    def _require_complete_config(self, db: Session, tenant_id: str, user_id: int | None = None) -> AiConfig:
        config = self._get_or_create_config(db, tenant_id, user_id)
        provider_profile = get_provider_profile(config.provider)
        missing = provider_profile.missing_config_fields(config.base_url, config.api_key, config.model)
        if missing:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": self.provider_error_codes["config"],
                    "message": f"AI 配置不完整：缺少 {', '.join(missing)}",
                    "provider": config.provider,
                    "recoverable": True,
                },
            )
        return config

    @staticmethod
    def _to_config_read(config: AiConfig) -> AiConfigRead:
        provider = AiProvider(config.provider or AiProvider.OPENAI_COMPATIBLE.value)
        profile = get_provider_profile(provider)
        return AiConfigRead(
            provider=provider,
            base_url=config.base_url or "",
            api_key=config.api_key or "",
            model=config.model or "",
            configured=profile.is_configured(config.base_url, config.api_key, config.model),
            provider_display_name=profile.display_name,
            provider_base_url_hint=profile.base_url_hint,
            provider_api_key_required=profile.api_key_required,
            provider_model_hint=profile.model_hint,
        )

    def _build_chat_payload(self, messages: list[AiChatMessage]) -> list[dict[str, str]]:
        return [{"role": "system", "content": self.investor_system_prompt}, *[message.model_dump() for message in messages]]

    def _build_agent_context(self, db: Session, payload: AiAgentRunRequest, user_id: int | None) -> dict[str, Any]:
        context = dict(payload.context)
        context.setdefault("warnings", [])
        if payload.agent_type.value == "parameter_advisor":
            self._attach_backtest_context(context, payload.result_ref, user_id)
        return context

    def _attach_backtest_context(self, context: dict[str, Any], result_ref: str | None, user_id: int | None) -> None:
        if not result_ref:
            return
        job = self.backtest_jobs.get(result_ref)
        if job and int((job.get("payload") or {}).get("user_id") or 0) == (user_id or 0):
            context["backtest_result"] = self._extract_backtest_result(job)
            return
        job = self.optimization_jobs.get(result_ref)
        if job and int((job.get("payload") or {}).get("user_id") or 0) == (user_id or 0):
            context["optimization_result"] = self._extract_optimization_result(job)
            return
        context["warnings"].append("未找到可用的回测或优化任务。")

    @staticmethod
    def _extract_backtest_result(job: dict[str, Any]) -> dict[str, Any]:
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        return {
            "job_id": job.get("job_id"),
            "status": job.get("status"),
            "result": result,
            "payload": job.get("payload") if isinstance(job.get("payload"), dict) else {},
        }

    @staticmethod
    def _extract_optimization_result(job: dict[str, Any]) -> dict[str, Any]:
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        best_candidate = result.get("best_candidate") if isinstance(result.get("best_candidate"), dict) else {}
        return {
            "job_id": job.get("job_id"),
            "status": job.get("status"),
            "result": result,
            "best_candidate": best_candidate,
            "payload": job.get("payload") if isinstance(job.get("payload"), dict) else {},
        }

    def _build_parameter_advice_context(self, payload: AiParameterAdviceRequest, user_id: int | None) -> dict[str, Any]:
        context: dict[str, Any] = {
            "symbol": payload.symbol,
            "strategy_type": payload.strategy_type,
            "current_parameters": payload.current_parameters,
            "warnings": [],
        }
        result_ref = payload.optimization_job_id or payload.backtest_job_id
        if result_ref:
            self._attach_backtest_context(context, result_ref, user_id)
        return context

    def _request_completion(self, config: AiConfig, messages: list[dict[str, str]]) -> str:
        provider_profile = self._validate_provider_config(config)
        try:
            with httpx.Client(timeout=self.model_request_timeout) as client:
                response = client.post(
                    provider_profile.build_chat_url(config.base_url),
                    headers=provider_profile.build_headers(config.api_key),
                    json=provider_profile.build_payload(config.model, messages),
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=502, detail={"code": self.provider_error_codes["timeout"], "message": f"AI 服务超时：{exc}", "provider": config.provider, "recoverable": True}) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400] if exc.response is not None else str(exc)
            raise HTTPException(status_code=502, detail={"code": self.provider_error_codes["http"], "message": f"AI 服务请求失败: {detail}", "provider": config.provider, "recoverable": True}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail={"code": self.provider_error_codes["http"], "message": f"AI 服务连接失败: {exc}", "provider": config.provider, "recoverable": True}) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail={"code": self.provider_error_codes["bad_payload"], "message": "AI 服务返回了无效响应", "provider": config.provider, "recoverable": True}) from exc

        content = extract_completion_text(payload)
        if not content:
            raise HTTPException(status_code=502, detail={"code": self.provider_error_codes["bad_payload"], "message": "AI 服务没有返回有效内容", "provider": config.provider, "recoverable": True})
        return content

    def _stream_completion(self, config: AiConfig, messages: list[dict[str, str]]) -> Iterator[str]:
        provider_profile = self._validate_provider_config(config)
        try:
            with httpx.Client(timeout=self.model_request_timeout) as client:
                with client.stream(
                    "POST",
                    provider_profile.build_chat_url(config.base_url),
                    headers=provider_profile.build_headers(config.api_key),
                    json=provider_profile.build_payload(config.model, messages, stream=True),
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
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=502, detail={"code": self.provider_error_codes["timeout"], "message": f"AI 流式请求超时：{exc}", "provider": config.provider, "recoverable": True}) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400] if exc.response is not None else str(exc)
            raise HTTPException(status_code=502, detail={"code": self.provider_error_codes["http"], "message": f"AI 流式请求失败: {detail}", "provider": config.provider, "recoverable": True}) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail={"code": self.provider_error_codes["http"], "message": f"AI 流式连接失败: {exc}", "provider": config.provider, "recoverable": True}) from exc

    def _validate_provider_config(self, config: AiConfig):
        provider_profile = get_provider_profile(config.provider)
        missing = provider_profile.missing_config_fields(config.base_url, config.api_key, config.model)
        if missing:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": self.provider_error_codes["config"],
                    "message": f"AI 配置不完整：缺少 {', '.join(missing)}",
                    "provider": config.provider,
                    "recoverable": True,
                },
            )
        return provider_profile

    def _prepare_stock_analysis(
        self,
        db: Session,
        tenant_id: str,
        symbol: str,
        note: str | None = None,
        user_id: int | None = None,
    ) -> tuple[AiConfig, AiStockAnalysisResponse, list[dict[str, str]]]:
        config = self._require_complete_config(db, tenant_id, user_id)
        normalized_symbol = normalize_a_share_symbol(symbol)
        security = find_security_by_symbol(normalized_symbol)
        if security is None:
            raise HTTPException(status_code=404, detail={"code": self.provider_error_codes["context"], "message": "未找到对应证券", "recoverable": False})

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
        payload = [{"role": "system", "content": self.stock_analysis_system_prompt}, {"role": "user", "content": prompt}]
        return config, response_stub, payload

    @staticmethod
    def _exception_detail(exc: HTTPException) -> str:
        detail = exc.detail
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("code") or detail)
        return str(detail)

    @staticmethod
    def _exception_code(exc: HTTPException) -> str | None:
        detail = exc.detail
        if isinstance(detail, dict):
            code = detail.get("code")
            return code if isinstance(code, str) and code else None
        return None
