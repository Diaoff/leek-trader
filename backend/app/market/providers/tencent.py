from __future__ import annotations

from datetime import date

import httpx

from app.market.providers.base import DailyBarSnapshot, PriceHistoryProvider, ProviderProfile, capability
from app.market.symbols import normalize_a_share_symbol


class TencentDailyBarProvider(PriceHistoryProvider):
    name = "tencent"
    endpoint = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    profile = ProviderProfile(
        name=name,
        label="腾讯证券",
        capabilities=(
            capability("daily_bar", supported=True, fields=("open", "high", "low", "close", "volume")),
        ),
        supports_adjustment=True,
        stable_for_backtest=False,
        rate_limit_note="公网接口，适合作为历史日线兜底",
        failure_modes=("网络超时", "qfqday 缺失", "返回结构变化"),
    )

    def fetch_daily_bars(self, symbol: str, limit: int = 60) -> list[DailyBarSnapshot]:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol:
            return []

        params = {
            "param": f"{normalized_symbol},day,,,{limit},qfq",
        }
        headers = {"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"}
        with httpx.Client(timeout=5.0) as client:
            response = client.get(self.endpoint, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        return self.parse_daily_bars(normalized_symbol, payload)

    @staticmethod
    def parse_daily_bars(symbol: str, payload: object) -> list[DailyBarSnapshot]:
        if not isinstance(payload, dict):
            return []

        data = payload.get("data", {})
        if not isinstance(data, dict):
            return []

        symbol_payload = data.get(symbol, {})
        if not isinstance(symbol_payload, dict):
            return []

        rows = symbol_payload.get("qfqday") or symbol_payload.get("day") or []
        if not isinstance(rows, list):
            return []

        bars: list[DailyBarSnapshot] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                continue
            try:
                bars.append(
                    DailyBarSnapshot(
                        symbol=symbol,
                        trade_date=date.fromisoformat(str(row[0])[:10]),
                        open_price=float(row[1]),
                        close_price=float(row[2]),
                        high_price=float(row[3]),
                        low_price=float(row[4]),
                        volume=float(row[5]),
                    )
                )
            except (TypeError, ValueError):
                continue
        return bars
