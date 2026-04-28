from dataclasses import dataclass, field
import json
import re
from typing import Any

import httpx

from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.service import QuoteRead, QuoteService

from .config import DEFAULT_AI_PROMPT_CONFIG


@dataclass(frozen=True)
class AiStockContext:
    quote: QuoteRead | None
    history_csv: str
    history_source: str = "none"
    news_items: list[str] = field(default_factory=list)
    discussion_items: list[str] = field(default_factory=list)


class AiDataLoader:
    def __init__(self, quote_service: QuoteService | None = None) -> None:
        self.quote_service = quote_service or QuoteService()

    def load_stock_context(self, symbol: str, history_limit: int = DEFAULT_AI_PROMPT_CONFIG.history_limit) -> AiStockContext:
        quote = next(iter(self.quote_service.list_quotes([symbol])), None)
        history_csv, history_source = self.fetch_recent_history_csv(symbol, history_limit)
        return AiStockContext(
            quote=quote,
            history_csv=history_csv,
            history_source=history_source,
            news_items=[],
            discussion_items=[],
        )

    def fetch_recent_history_csv(self, symbol: str, limit: int = DEFAULT_AI_PROMPT_CONFIG.history_limit) -> tuple[str, str]:
        eastmoney_csv = self._fetch_eastmoney_history_csv(symbol, limit)
        if eastmoney_csv:
            return eastmoney_csv, "东方财富前复权日线"

        sina_csv = self._fetch_sina_history_csv(symbol, limit)
        if sina_csv:
            return sina_csv, "新浪日线"

        return "", "none"

    def _fetch_eastmoney_history_csv(self, symbol: str, limit: int) -> str:
        params = {
            "secid": EastMoneyQuoteProvider._to_secid(symbol),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "lmt": str(limit),
            "end": "20500101",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(EastMoneyQuoteProvider.kline_endpoint, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return ""

        return self._klines_to_csv(payload)

    def _fetch_sina_history_csv(self, symbol: str, limit: int) -> str:
        params = {
            "symbol": symbol,
            "scale": "240",
            "ma": "no",
            "datalen": str(limit),
        }
        headers = {
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0",
        }

        try:
            with httpx.Client(timeout=10.0, headers=headers) as client:
                response = client.get(
                    "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData",
                    params=params,
                )
                response.raise_for_status()
        except Exception:
            return ""

        return self._sina_kline_to_csv(response.text)

    @staticmethod
    def _klines_to_csv(payload: dict[str, Any]) -> str:
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

    @staticmethod
    def _sina_kline_to_csv(payload: str) -> str:
        match = re.search(r"=\((\[.*\])\)\s*;?", payload, flags=re.S)
        if match is None:
            return ""

        try:
            items = json.loads(match.group(1))
        except ValueError:
            return ""

        if not isinstance(items, list) or not items:
            return ""

        rows = ["日期,开盘,收盘,最高,最低,成交量"]
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                ",".join(
                    [
                        str(item.get("day", "")),
                        str(item.get("open", "")),
                        str(item.get("close", "")),
                        str(item.get("high", "")),
                        str(item.get("low", "")),
                        str(item.get("volume", "")),
                    ]
                )
            )
        return "\n".join(row for row in rows if row and not row.startswith(","))
