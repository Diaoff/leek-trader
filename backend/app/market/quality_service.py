from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market.symbols import normalize_a_share_symbol
from app.models.market_daily_bar import MarketDailyBar


@dataclass(slots=True)
class MarketDataQualitySymbolReport:
    symbol: str
    rows: int
    first_trade_date: str | None
    last_trade_date: str | None
    suspended_rows: int
    st_rows: int
    null_counts: dict[str, int]
    calendar_gap_days: list[str]


@dataclass(slots=True)
class MarketDataQualityReport:
    status: str
    source: str
    adjustflag: str
    symbols: list[str]
    start_date: str | None
    end_date: str | None
    total_rows: int
    field_count: int
    nullable_fields: list[str]
    symbol_reports: list[MarketDataQualitySymbolReport]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "source": self.source,
            "adjustflag": self.adjustflag,
            "symbols": self.symbols,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_rows": self.total_rows,
            "field_count": self.field_count,
            "nullable_fields": self.nullable_fields,
            "symbol_reports": [
                {
                    "symbol": report.symbol,
                    "rows": report.rows,
                    "first_trade_date": report.first_trade_date,
                    "last_trade_date": report.last_trade_date,
                    "suspended_rows": report.suspended_rows,
                    "st_rows": report.st_rows,
                    "null_counts": report.null_counts,
                    "calendar_gap_days": report.calendar_gap_days,
                }
                for report in self.symbol_reports
            ],
        }


class MarketDataQualityService:
    nullable_fields = [
        "amplitude_pct",
        "change_pct",
        "turnover_rate",
        "preclose",
        "trade_status",
        "pe_ttm",
        "pb_mrq",
        "ps_ttm",
        "pcf_ncf_ttm",
        "is_st",
    ]

    def __init__(self, db: Session) -> None:
        self.db = db

    def build_daily_bar_quality_report(
        self,
        *,
        symbols: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
    ) -> MarketDataQualityReport:
        normalized_symbols: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized = normalize_a_share_symbol(symbol)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_symbols.append(normalized)

        query = select(MarketDailyBar).where(MarketDailyBar.source == source, MarketDailyBar.adjustflag == adjustflag)
        if normalized_symbols:
            query = query.where(MarketDailyBar.symbol.in_(normalized_symbols))
        if start_date is not None:
            query = query.where(MarketDailyBar.trade_date >= start_date)
        if end_date is not None:
            query = query.where(MarketDailyBar.trade_date <= end_date)
        rows = self.db.scalars(query.order_by(MarketDailyBar.symbol.asc(), MarketDailyBar.trade_date.asc())).all()

        rows_by_symbol: dict[str, list[MarketDailyBar]] = {}
        for row in rows:
            rows_by_symbol.setdefault(row.symbol, []).append(row)

        reports: list[MarketDataQualitySymbolReport] = []
        for symbol in normalized_symbols or sorted(rows_by_symbol):
            symbol_rows = rows_by_symbol.get(symbol, [])
            trade_dates = [row.trade_date for row in symbol_rows]
            reports.append(
                MarketDataQualitySymbolReport(
                    symbol=symbol,
                    rows=len(symbol_rows),
                    first_trade_date=min(trade_dates).isoformat() if trade_dates else None,
                    last_trade_date=max(trade_dates).isoformat() if trade_dates else None,
                    suspended_rows=sum(1 for row in symbol_rows if row.trade_status != 1),
                    st_rows=sum(1 for row in symbol_rows if row.is_st is True),
                    null_counts={field: self._null_count(symbol_rows, field) for field in self.nullable_fields},
                    calendar_gap_days=self._calendar_gap_days(trade_dates),
                )
            )

        return MarketDataQualityReport(
            status="ready" if rows else "empty",
            source=source,
            adjustflag=adjustflag,
            symbols=normalized_symbols or sorted(rows_by_symbol),
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            total_rows=len(rows),
            field_count=len(self.nullable_fields),
            nullable_fields=list(self.nullable_fields),
            symbol_reports=reports,
        )

    @staticmethod
    def _null_count(rows: list[MarketDailyBar], field: str) -> int:
        return sum(1 for row in rows if getattr(row, field) is None)

    @staticmethod
    def _calendar_gap_days(trade_dates: list[date]) -> list[str]:
        if len(trade_dates) < 2:
            return []
        sorted_dates = sorted(set(trade_dates))
        gaps: list[str] = []
        for previous_date, current_date in zip(sorted_dates, sorted_dates[1:]):
            cursor = previous_date + timedelta(days=1)
            while cursor < current_date:
                gaps.append(cursor.isoformat())
                cursor += timedelta(days=1)
        return gaps
