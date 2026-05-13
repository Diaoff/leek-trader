import logging
import re
from datetime import date, datetime, timezone

import httpx

from app.market.providers.base import DailyBarSnapshot, PriceHistoryProvider, ProviderProfile, QuoteProvider, QuoteSnapshot, capability
from app.market.symbols import normalize_a_share_symbol

QUOTE_PATTERN = re.compile(r'var hq_str_(?P<symbol>[^=]+)="(?P<body>[^"]*)";')
logger = logging.getLogger(__name__)
SINA_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "http://finance.sina.com.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


class SinaQuoteProvider(QuoteProvider):
    name = "sina"
    endpoint = "https://hq.sinajs.cn/list="
    profile = ProviderProfile(
        name=name,
        label="新浪财经",
        capabilities=(
            capability("quote", supported=True, fields=("price", "change_percent", "volume")),
            capability("daily_bar", supported=True, fields=("open", "high", "low", "close", "volume"), notes=("由 SinaDailyBarProvider 提供",)),
        ),
        stable_for_backtest=False,
        rate_limit_note="公网接口，适合轻量行情兜底",
        failure_modes=("网络超时", "空字符串响应", "字段位置变化"),
    )

    def fetch_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        target_symbols = [symbol.strip().lower() for symbol in symbols if symbol.strip()]
        if not target_symbols:
            return []
        try:
            with httpx.Client(timeout=5.0, headers=SINA_REQUEST_HEADERS) as client:
                response = client.get(f"{self.endpoint}{','.join(target_symbols)}")
                response.raise_for_status()
        except httpx.HTTPStatusError as error:
            logger.warning(
                "Sina quote request failed with status %s for symbols=%s",
                error.response.status_code,
                ",".join(target_symbols),
            )
            raise
        except httpx.HTTPError:
            logger.warning(
                "Sina quote request failed for symbols=%s",
                ",".join(target_symbols),
                exc_info=True,
            )
            raise
        return self.parse_response(self._decode_payload(response.content))

    def parse_response(self, payload: str) -> list[QuoteSnapshot]:
        snapshots: list[QuoteSnapshot] = []
        for match in QUOTE_PATTERN.finditer(payload):
            symbol = match.group("symbol")
            body = match.group("body")
            fields = body.split(",")
            if len(fields) < 32 or not fields[3]:
                continue
            previous_close = self._to_float(fields[2])
            price = self._to_float(fields[3])
            volume = self._to_float(fields[8])
            timestamp = self._parse_timestamp(fields[30], fields[31])
            change_percent = 0.0
            if previous_close > 0:
                change_percent = round((price - previous_close) / previous_close * 100, 2)
            snapshots.append(
                QuoteSnapshot(
                    symbol=symbol,
                    price=price,
                    change_percent=change_percent,
                    volume=volume,
                    timestamp=timestamp,
                    is_halted=price <= 0,
                )
            )
        return snapshots

    @staticmethod
    def _to_float(value: str) -> float:
        try:
            return float(value)
        except ValueError:
            return 0.0

    @staticmethod
    def _decode_payload(payload: bytes) -> str:
        return payload.decode("gb18030", errors="ignore")

    @staticmethod
    def _parse_timestamp(date_value: str, time_value: str) -> datetime:
        if not date_value or not time_value:
            return datetime.now(timezone.utc)
        return datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


class SinaDailyBarProvider(PriceHistoryProvider):
    name = "sina"
    endpoint = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

    def fetch_daily_bars(self, symbol: str, limit: int = 60) -> list[DailyBarSnapshot]:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol:
            return []

        params = {
            "symbol": normalized_symbol,
            "scale": "10080",
            "ma": "no",
            "datalen": str(limit),
        }
        headers = {"Referer": "http://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
        with httpx.Client(timeout=5.0) as client:
            response = client.get(self.endpoint, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        return self.parse_daily_bars(normalized_symbol, payload)

    @staticmethod
    def parse_daily_bars(symbol: str, payload: object) -> list[DailyBarSnapshot]:
        if not isinstance(payload, list):
            return []

        bars: list[DailyBarSnapshot] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            trade_day = str(row.get("day", "") or row.get("date", "")).strip()
            if not trade_day:
                continue
            try:
                bars.append(
                    DailyBarSnapshot(
                        symbol=symbol,
                        trade_date=date.fromisoformat(trade_day[:10]),
                        open_price=float(row.get("open", 0)),
                        close_price=float(row.get("close", 0)),
                        high_price=float(row.get("high", 0)),
                        low_price=float(row.get("low", 0)),
                        volume=float(row.get("volume", 0)),
                    )
                )
            except (TypeError, ValueError):
                continue
        return bars
