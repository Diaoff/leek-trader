from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.baostock import BaoStockDailyBarProvider, BaoStockLoginError
from app.market.symbols import normalize_a_share_symbol

logger = logging.getLogger(__name__)

BaoStockSyncProgressCallback = Callable[[int, int, str, list[str]], None]


@dataclass(slots=True)
class BaoStockSyncFailure:
    symbol: str
    reason: str


@dataclass(slots=True)
class BaoStockSyncRange:
    symbol: str
    start_date: str
    end_date: str
    skipped: bool = False
    reason: str | None = None


@dataclass(slots=True)
class BaoStockSyncResult:
    status: str
    source: str
    adjustflag: str
    start_date: str
    end_date: str
    requested_symbols: list[str]
    incremental: bool = False
    resolved_ranges: list[BaoStockSyncRange] = field(default_factory=list)
    succeeded_symbols: list[str] = field(default_factory=list)
    failures: list[BaoStockSyncFailure] = field(default_factory=list)
    bars_upserted: int = 0

    @property
    def success_count(self) -> int:
        return len(self.succeeded_symbols)

    @property
    def failure_count(self) -> int:
        return len(self.failures)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "source": self.source,
            "adjustflag": self.adjustflag,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "requested_symbols": self.requested_symbols,
            "incremental": self.incremental,
            "resolved_ranges": [
                {
                    "symbol": item.symbol,
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                    "skipped": item.skipped,
                    "reason": item.reason,
                }
                for item in self.resolved_ranges
            ],
            "succeeded_symbols": self.succeeded_symbols,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "failures": [{"symbol": failure.symbol, "reason": failure.reason} for failure in self.failures],
            "bars_upserted": self.bars_upserted,
        }


class BaoStockHistorySyncService:
    def __init__(self, db: Session, *, provider: BaoStockDailyBarProvider | None = None) -> None:
        self.db = db
        self.provider = provider
        self.storage = MarketDailyBarStorage(db)

    def sync_history(
        self,
        *,
        symbols: list[str],
        start_date: date,
        end_date: date,
        adjustflag: str = "2",
        incremental: bool = False,
        progress_callback: BaoStockSyncProgressCallback | None = None,
    ) -> BaoStockSyncResult:
        normalized_symbols = self._normalize_symbols(symbols)
        if not normalized_symbols:
            raise ValueError("symbols must be a non-empty explicit list")
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")

        provider = self.provider or BaoStockDailyBarProvider(adjustflag=adjustflag)
        provider.adjustflag = adjustflag
        result = BaoStockSyncResult(
            status="completed",
            source=provider.name,
            adjustflag=adjustflag,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            requested_symbols=normalized_symbols,
            incremental=incremental,
        )

        try:
            total_symbols = len(normalized_symbols)
            for index, symbol in enumerate(normalized_symbols, start=1):
                symbol_start_date = self._resolve_symbol_start_date(
                    symbol=symbol,
                    source=provider.name,
                    adjustflag=adjustflag,
                    requested_start_date=start_date,
                    incremental=incremental,
                )
                if symbol_start_date > end_date:
                    self._emit_progress(
                        progress_callback,
                        index,
                        total_symbols,
                        f"跳过 {symbol} 日线",
                        ["原因：已同步到最新交易日", f"日期范围：{symbol_start_date.isoformat()} ~ {end_date.isoformat()}"],
                    )
                    result.resolved_ranges.append(
                        BaoStockSyncRange(
                            symbol=symbol,
                            start_date=symbol_start_date.isoformat(),
                            end_date=end_date.isoformat(),
                            skipped=True,
                            reason="already_up_to_date",
                        )
                    )
                    result.succeeded_symbols.append(symbol)
                    continue

                result.resolved_ranges.append(
                    BaoStockSyncRange(
                        symbol=symbol,
                        start_date=symbol_start_date.isoformat(),
                        end_date=end_date.isoformat(),
                    )
                )
                try:
                    self._emit_progress(
                        progress_callback,
                        index,
                        total_symbols,
                        f"正在获取 {symbol} 日线",
                        [f"日期范围：{symbol_start_date.isoformat()} ~ {end_date.isoformat()}", f"复权：{adjustflag}"],
                    )
                    bars = provider.fetch_daily_bars_range(symbol, start_date=symbol_start_date, end_date=end_date)
                    upserted = self.storage.upsert_bars(bars, source=provider.name, adjustflag=adjustflag)
                    result.bars_upserted += upserted
                    result.succeeded_symbols.append(symbol)
                    self._emit_progress(
                        progress_callback,
                        index,
                        total_symbols,
                        f"已保存 {symbol} 日线",
                        [f"本次获取：{len(bars)} 条", f"本次入库：{upserted} 条", f"累计入库：{result.bars_upserted} 条"],
                    )
                except Exception as error:
                    logger.warning("BaoStock history sync failed symbol=%s error=%s", symbol, error)
                    result.failures.append(BaoStockSyncFailure(symbol=symbol, reason=str(error)))
                    self._emit_progress(
                        progress_callback,
                        index,
                        total_symbols,
                        f"获取 {symbol} 日线失败",
                        [str(error)],
                    )
                    if isinstance(error, BaoStockLoginError):
                        result.failures.extend(
                            BaoStockSyncFailure(symbol=remaining_symbol, reason=f"skipped after BaoStock login failure: {error}")
                            for remaining_symbol in normalized_symbols[index:]
                        )
                        break
        finally:
            close = getattr(provider, "close", None)
            if callable(close):
                close()

        if result.failure_count and result.success_count:
            result.status = "partial_success"
        elif result.failure_count:
            result.status = "failed"
        return result

    @staticmethod
    def _emit_progress(
        callback: BaoStockSyncProgressCallback | None,
        step: int,
        total: int,
        label: str,
        details: list[str] | None = None,
    ) -> None:
        if callback is not None:
            callback(step, total, label, details or [])

    def _resolve_symbol_start_date(
        self,
        *,
        symbol: str,
        source: str,
        adjustflag: str,
        requested_start_date: date,
        incremental: bool,
    ) -> date:
        if not incremental:
            return requested_start_date
        latest_trade_date = self.storage.latest_trade_date(symbol=symbol, source=source, adjustflag=adjustflag)
        if latest_trade_date is None:
            return requested_start_date
        return max(requested_start_date, latest_trade_date + timedelta(days=1))

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized_symbol = normalize_a_share_symbol(symbol)
            if not normalized_symbol or normalized_symbol in seen:
                continue
            seen.add(normalized_symbol)
            normalized.append(normalized_symbol)
        return normalized
