from __future__ import annotations

from datetime import date
from types import ModuleType
from typing import Any

from app.market.providers.base import DailyBarSnapshot, PriceHistoryProvider
from app.market.symbols import normalize_a_share_symbol


BAOSTOCK_FIELDS = ",".join(
    [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "adjustflag",
        "turn",
        "tradestatus",
        "pctChg",
        "peTTM",
        "pbMRQ",
        "psTTM",
        "pcfNcfTTM",
        "isST",
    ]
)


class BaoStockDailyBarProvider(PriceHistoryProvider):
    name = "baostock"

    def __init__(self, *, adjustflag: str = "2", baostock_module: ModuleType | Any | None = None) -> None:
        self.adjustflag = adjustflag
        self._baostock = baostock_module

    def fetch_daily_bars(self, symbol: str, limit: int = 60) -> list[DailyBarSnapshot]:
        bars = self.fetch_daily_bars_range(symbol, start_date=date(1990, 1, 1), end_date=date.today())
        if limit > 0:
            return bars[-limit:]
        return bars

    def fetch_daily_bars_range(self, symbol: str, *, start_date: date, end_date: date) -> list[DailyBarSnapshot]:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol:
            return []

        baostock = self._load_baostock()
        login_result = baostock.login()
        if getattr(login_result, "error_code", "0") != "0":
            raise RuntimeError(f"baostock login failed: {getattr(login_result, 'error_msg', '')}")

        try:
            result = baostock.query_history_k_data_plus(
                self.to_baostock_symbol(normalized_symbol),
                BAOSTOCK_FIELDS,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                frequency="d",
                adjustflag=self.adjustflag,
            )
            if getattr(result, "error_code", "0") != "0":
                raise RuntimeError(f"baostock history query failed: {getattr(result, 'error_msg', '')}")
            rows = result.get_data()
        finally:
            baostock.logout()

        return self.parse_daily_bars(normalized_symbol, rows)

    def _load_baostock(self) -> ModuleType | Any:
        if self._baostock is not None:
            return self._baostock
        try:
            import baostock as baostock  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("baostock is not installed; install backend requirements to use source=baostock") from error
        self._baostock = baostock
        return baostock

    @staticmethod
    def to_baostock_symbol(symbol: str) -> str:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if normalized_symbol.startswith("sh"):
            return f"sh.{normalized_symbol[2:]}"
        if normalized_symbol.startswith("sz"):
            return f"sz.{normalized_symbol[2:]}"
        if normalized_symbol.startswith("bj"):
            return f"bj.{normalized_symbol[2:]}"
        return normalized_symbol

    @classmethod
    def parse_daily_bars(cls, symbol: str, rows: Any) -> list[DailyBarSnapshot]:
        normalized_symbol = normalize_a_share_symbol(symbol)
        records = cls._iter_records(rows)
        bars: list[DailyBarSnapshot] = []
        for row in records:
            trade_day = str(row.get("date", "")).strip()
            if not trade_day:
                continue
            try:
                bars.append(
                    DailyBarSnapshot(
                        symbol=normalized_symbol,
                        trade_date=date.fromisoformat(trade_day[:10]),
                        open_price=cls._to_float(row.get("open")),
                        close_price=cls._to_float(row.get("close")),
                        high_price=cls._to_float(row.get("high")),
                        low_price=cls._to_float(row.get("low")),
                        volume=cls._to_float(row.get("volume")),
                        turnover=cls._to_float(row.get("amount")),
                        change_pct=cls._optional_float(row.get("pctChg")),
                        turnover_rate=cls._optional_float(row.get("turn")),
                        preclose=cls._optional_float(row.get("preclose")),
                        trade_status=cls._optional_int(row.get("tradestatus")),
                        pe_ttm=cls._optional_float(row.get("peTTM")),
                        pb_mrq=cls._optional_float(row.get("pbMRQ")),
                        ps_ttm=cls._optional_float(row.get("psTTM")),
                        pcf_ncf_ttm=cls._optional_float(row.get("pcfNcfTTM")),
                        is_st=cls._optional_bool(row.get("isST")),
                    )
                )
            except (TypeError, ValueError):
                continue
        return bars

    @staticmethod
    def _iter_records(rows: Any) -> list[dict[str, Any]]:
        if rows is None:
            return []
        if hasattr(rows, "to_dict"):
            return list(rows.to_dict("records"))
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        return []

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _optional_float(cls, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _optional_int(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _optional_bool(cls, value: Any) -> bool | None:
        parsed = cls._optional_int(value)
        if parsed is None:
            return None
        return parsed == 1
