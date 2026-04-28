import json
from datetime import UTC, date, datetime
from functools import lru_cache

import httpx

from app.market.providers.base import DailyBarSnapshot, PriceHistoryProvider, QuoteProvider, QuoteSnapshot


class EastMoneyQuoteProvider(QuoteProvider, PriceHistoryProvider):
    name = "eastmoney"
    endpoint = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    kline_endpoint = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    def fetch_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        target_symbols = [symbol.strip().lower() for symbol in symbols if symbol.strip()]
        if not target_symbols:
            return []
        params = {
            "secids": ",".join(self._to_secid(symbol) for symbol in target_symbols),
            "fltt": "2",
            "invt": "2",
            "fields": "f12,f14,f2,f3,f6,f13,f20",
        }
        with httpx.Client(timeout=5.0) as client:
            response = client.get(self.endpoint, params=params)
            response.raise_for_status()
            snapshots = self.parse_response(response.text)

        for snapshot in snapshots:
            snapshot.ytd_change_percent = self._get_ytd_change_percent(snapshot.symbol, snapshot.price)

        return snapshots

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
            market_cap = self._to_float(item.get("f20"))
            snapshots.append(
                QuoteSnapshot(
                    symbol=symbol,
                    price=price,
                    change_percent=change_percent,
                    volume=volume,
                    timestamp=datetime.now(UTC),
                    is_halted=price <= 0,
                    market_cap=market_cap if market_cap > 0 else None,
                )
            )
        return snapshots

    def fetch_daily_bars(self, symbol: str, limit: int = 60) -> list[DailyBarSnapshot]:
        params = {
            "secid": self._to_secid(symbol),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "lmt": str(limit),
            "end": "20500101",
        }

        with httpx.Client(timeout=5.0) as client:
            response = client.get(self.kline_endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        klines = payload.get("data", {}).get("klines", []) or []
        return self.parse_daily_bars(symbol, klines)

    def parse_daily_bars(self, symbol: str, klines: list[str]) -> list[DailyBarSnapshot]:
        bars: list[DailyBarSnapshot] = []
        for row in klines:
            parts = str(row).split(",")
            if len(parts) < 11:
                continue
            try:
                bars.append(
                    DailyBarSnapshot(
                        symbol=symbol,
                        trade_date=date.fromisoformat(parts[0]),
                        open_price=self._to_float(parts[1]),
                        close_price=self._to_float(parts[2]),
                        high_price=self._to_float(parts[3]),
                        low_price=self._to_float(parts[4]),
                        volume=self._to_float(parts[5]),
                        turnover=self._to_float(parts[6]),
                        amplitude_pct=self._to_float(parts[7]),
                        change_pct=self._to_float(parts[8]),
                        turnover_rate=self._to_float(parts[10]),
                    )
                )
            except ValueError:
                continue
        return bars

    def _get_ytd_change_percent(self, symbol: str, latest_price: float) -> float | None:
        if latest_price <= 0:
            return None

        reference_close = self._get_ytd_reference_close(symbol, date.today().year)
        if reference_close is None or reference_close <= 0:
            return None

        return round(((latest_price / reference_close) - 1) * 100, 2)

    @staticmethod
    def _to_secid(symbol: str) -> str:
        if symbol.startswith("sh"):
            return f"1.{symbol[2:]}"
        if symbol.startswith("sz"):
            return f"0.{symbol[2:]}"
        if symbol.startswith("bj"):
            return f"0.{symbol[2:]}"
        return f"1.{symbol}"

    @staticmethod
    def _from_market_code(market: str, code: str) -> str:
        return ("sh" if market == "1" else "sz") + code

    @staticmethod
    def _to_price(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    @lru_cache(maxsize=2048)
    def _get_ytd_reference_close(cls, symbol: str, year: int) -> float | None:
        params = {
            "secid": cls._to_secid(symbol),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "end": f"{year}1231",
            "lmt": "260",
        }

        with httpx.Client(timeout=5.0) as client:
            response = client.get(cls.kline_endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        klines = payload.get("data", {}).get("klines", []) or []
        for row in klines:
            parts = str(row).split(",")
            if len(parts) < 3:
                continue
            if not parts[0].startswith(str(year)):
                continue
            close = cls._to_float(parts[2])
            if close > 0:
                return close
        return None
