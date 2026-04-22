import json
from datetime import datetime, timezone

import httpx

from app.market.providers.base import QuoteProvider, QuoteSnapshot


class EastMoneyQuoteProvider(QuoteProvider):
    name = "eastmoney"
    endpoint = "https://push2.eastmoney.com/api/qt/ulist.np/get"

    def fetch_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        target_symbols = symbols or ["sh600519", "sz000001"]
        params = {
            "secids": ",".join(self._to_secid(symbol) for symbol in target_symbols),
            "fields": "f12,f14,f2,f3,f6,f13",
        }
        with httpx.Client(timeout=5.0) as client:
            response = client.get(self.endpoint, params=params)
            response.raise_for_status()
        return self.parse_response(response.text)

    def parse_response(self, payload: str) -> list[QuoteSnapshot]:
        data = json.loads(payload)
        diff = data.get("data", {}).get("diff", []) or []
        snapshots: list[QuoteSnapshot] = []
        for item in diff:
            market = str(item.get("f13", "1"))
            code = str(item.get("f12", ""))
            if not code:
                continue
            symbol = self._from_market_code(market, code)
            price = self._to_price(item.get("f2"))
            change_percent = self._to_float(item.get("f3"))
            volume = self._to_float(item.get("f6"))
            snapshots.append(
                QuoteSnapshot(
                    symbol=symbol,
                    price=price,
                    change_percent=change_percent,
                    volume=volume,
                    timestamp=datetime.now(timezone.utc),
                    is_halted=price <= 0,
                )
            )
        return snapshots

    @staticmethod
    def _to_secid(symbol: str) -> str:
        if symbol.startswith("sh"):
            return f"1.{symbol[2:]}"
        if symbol.startswith("sz"):
            return f"0.{symbol[2:]}"
        return f"1.{symbol}"

    @staticmethod
    def _from_market_code(market: str, code: str) -> str:
        return ("sh" if market == "1" else "sz") + code

    @staticmethod
    def _to_price(value: object) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(number / 100 if number > 10000 else number, 4)

    @staticmethod
    def _to_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
