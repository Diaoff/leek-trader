import json
from datetime import UTC, datetime
from typing import Any, Iterator

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.security_catalog import find_security_by_symbol
from app.market.service import QuoteService
from app.models.ai_config import AiConfig
from app.schemas.ai import (
    AiChatMessage,
    AiConfigRead,
    AiConfigUpdate,
    AiSecurityRead,
    AiStockAnalysisResponse,
)


class AiAnalysisService:
    model_request_timeout = 180.0
    investor_system_prompt = (
        "你是一名经验丰富的中文投资研究助手，擅长解读 A 股行情、量价结构与风险点。"
        "回答必须使用中文，结构清晰，避免空泛口号，不要编造未提供的数据。"
        "你的输出仅用于研究交流，不构成投资建议。"
    )

    stock_analysis_system_prompt = (
        "你是一名严谨的中文股票分析师。请依据给定的证券资料、实时行情和历史日线，"
        "输出客观、可执行的研究结论。若数据不足，请明确指出缺口。"
    )

    def __init__(self) -> None:
        self.quote_service = QuoteService()

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

        content = self._extract_completion_text(payload)
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
                        content = self._extract_completion_text(payload)
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

                        chunk = self._extract_stream_text(payload)
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

    @staticmethod
    def _extract_completion_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return ""

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and item.get("text"):
                    fragments.append(str(item["text"]))
            return "\n".join(fragment.strip() for fragment in fragments if fragment).strip()
        return ""

    @staticmethod
    def _extract_stream_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return ""

        delta = choices[0].get("delta", {})
        if not isinstance(delta, dict):
            return ""

        content = delta.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and item.get("text"):
                    fragments.append(str(item["text"]))
            return "".join(fragments)
        return ""

    def _prepare_stock_analysis(
        self,
        db: Session,
        tenant_id: str,
        symbol: str,
        note: str | None = None,
    ) -> tuple[AiConfig, AiStockAnalysisResponse, list[dict[str, str]]]:
        config = self._require_complete_config(db, tenant_id)
        normalized_symbol = symbol.strip().lower()
        security = find_security_by_symbol(normalized_symbol)
        if security is None:
            raise HTTPException(status_code=404, detail="未找到对应证券")

        quote = next(iter(self.quote_service.list_quotes([normalized_symbol])), None)
        history_csv = self._fetch_recent_history_csv(normalized_symbol)
        prompt = self._build_stock_analysis_prompt(security, quote, history_csv, note)

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
            latest_price=quote.price if quote else None,
            change_percent=quote.change_percent if quote else None,
        )
        payload = [
            {"role": "system", "content": self.stock_analysis_system_prompt},
            {"role": "user", "content": prompt},
        ]
        return config, response_stub, payload

    def _fetch_recent_history_csv(self, symbol: str, limit: int = 60) -> str:
        params = {
            "secid": EastMoneyQuoteProvider._to_secid(symbol),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "lmt": str(limit),
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(EastMoneyQuoteProvider.kline_endpoint, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return ""

        klines = payload.get("data", {}).get("klines", []) or []
        if not klines:
            return ""

        rows = ["日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率"]
        for item in klines:
            parts = str(item).split(",")
            if len(parts) < 11:
                continue
            rows.append(",".join(parts[:11]))
        return "\n".join(rows)

    def _build_stock_analysis_prompt(
        self,
        security: dict[str, Any],
        quote: Any | None,
        history_csv: str,
        note: str | None,
    ) -> str:
        quote_lines = [
            f"证券名称：{security['name']}",
            f"证券代码：{security['code']} ({security['symbol']})",
            f"所属市场：{security['market']}",
            f"标签：{', '.join(str(tag) for tag in security.get('tags', [])) or '无'}",
        ]

        if quote is not None:
            quote_lines.extend(
                [
                    f"最新价格：{quote.price}",
                    f"当日涨跌幅：{quote.change_percent}%",
                    f"成交额/成交量字段：{quote.volume}",
                    f"总市值：{quote.market_cap if quote.market_cap is not None else '暂无'}",
                    f"年初至今涨跌幅：{quote.ytd_change_percent if quote.ytd_change_percent is not None else '暂无'}",
                ]
            )
        else:
            quote_lines.append("实时行情：暂无")

        if note:
            quote_lines.append(f"用户备注：{note.strip()}")

        history_block = history_csv or "暂无可用历史日线数据。"

        return (
            "请基于以下股票资料给出一份中文研究摘要。\n"
            "输出结构必须包含：\n"
            "1. 核心结论\n"
            "2. 趋势与量价观察\n"
            "3. 可能催化与驱动\n"
            "4. 主要风险点\n"
            "5. 后续观察清单\n"
            "要求：\n"
            "- 明确指出结论依据来自哪些已给数据\n"
            "- 不要虚构新闻、公告或财务数据\n"
            "- 若历史数据不足，请直接说明\n\n"
            f"{chr(10).join(quote_lines)}\n\n"
            f"近 60 个交易日复权日线 CSV：\n{history_block}"
        )
