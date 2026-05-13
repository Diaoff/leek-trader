from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.market.data_service import SOURCE_LABELS
from app.market.symbols import normalize_a_share_symbol
from app.models.market_daily_bar import MarketDailyBar

DEFAULT_HISTORY_SOURCE_PRIORITY = ["baostock", "tencent", "sina", "eastmoney"]


@dataclass(slots=True)
class MarketSourceHealthItem:
    source: str
    label: str
    status: str
    role: str
    symbol_count: int
    row_count: int
    first_trade_date: str | None
    last_trade_date: str | None
    missing_symbols: list[str]
    staleness_days: int | None
    health_level: str
    coverage_ratio: float
    empty_ratio: float
    field_missing_ratio: float
    freshness_score: float
    notes: list[str]


@dataclass(slots=True)
class MarketSourceHealthReport:
    status: str
    symbols: list[str]
    start_date: str | None
    end_date: str | None
    adjustflag: str
    primary_source: str | None
    fallback_sources: list[str]
    failover_policy: dict[str, object]
    sources: list[MarketSourceHealthItem]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "symbols": self.symbols,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "adjustflag": self.adjustflag,
            "primary_source": self.primary_source,
            "fallback_sources": self.fallback_sources,
            "failover_policy": self.failover_policy,
            "sources": [
                {
                    "source": item.source,
                    "label": item.label,
                    "status": item.status,
                    "role": item.role,
                    "symbol_count": item.symbol_count,
                    "row_count": item.row_count,
                    "first_trade_date": item.first_trade_date,
                    "last_trade_date": item.last_trade_date,
                    "missing_symbols": item.missing_symbols,
                    "staleness_days": item.staleness_days,
                    "health_level": item.health_level,
                    "coverage_ratio": item.coverage_ratio,
                    "empty_ratio": item.empty_ratio,
                    "field_missing_ratio": item.field_missing_ratio,
                    "freshness_score": item.freshness_score,
                    "notes": item.notes,
                }
                for item in self.sources
            ],
        }


class MarketSourceHealthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build_daily_bar_source_health(
        self,
        *,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        adjustflag: str = "2",
        sources: list[str] | None = None,
        stale_after_days: int = 5,
    ) -> MarketSourceHealthReport:
        normalized_symbols = self._normalize_symbols(symbols or [])
        candidate_sources = self._normalize_sources(sources or DEFAULT_HISTORY_SOURCE_PRIORITY)
        items = [
            self._build_source_item(
                source=source,
                symbols=normalized_symbols,
                start_date=start_date,
                end_date=end_date,
                adjustflag=adjustflag,
                stale_after_days=stale_after_days,
            )
            for source in candidate_sources
        ]
        primary_source = next((item.source for item in items if item.status == "healthy"), None)
        fallback_sources = [item.source for item in items if item.source != primary_source and item.status in {"healthy", "partial"}]
        for item in items:
            if item.source == primary_source:
                item.role = "primary"
            elif item.source in fallback_sources:
                item.role = "fallback"
            else:
                item.role = "unavailable"

        return MarketSourceHealthReport(
            status="healthy" if primary_source else "degraded" if fallback_sources else "empty",
            symbols=normalized_symbols,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            adjustflag=adjustflag,
            primary_source=primary_source,
            fallback_sources=fallback_sources,
            failover_policy={
                "scope": "daily_bars",
                "priority": candidate_sources,
                "selection": "first healthy source by priority; partial sources are fallback only",
                "stale_after_days": stale_after_days,
                "network_probe": False,
                "note": "本报告基于本地已落库日线数据，不主动请求外部数据源。",
            },
            sources=items,
        )

    def _build_source_item(
        self,
        *,
        source: str,
        symbols: list[str],
        start_date: date | None,
        end_date: date | None,
        adjustflag: str,
        stale_after_days: int,
    ) -> MarketSourceHealthItem:
        query = select(
            func.count(MarketDailyBar.id),
            func.count(func.distinct(MarketDailyBar.symbol)),
            func.min(MarketDailyBar.trade_date),
            func.max(MarketDailyBar.trade_date),
        ).where(MarketDailyBar.source == source, MarketDailyBar.adjustflag == adjustflag)
        if symbols:
            query = query.where(MarketDailyBar.symbol.in_(symbols))
        if start_date is not None:
            query = query.where(MarketDailyBar.trade_date >= start_date)
        if end_date is not None:
            query = query.where(MarketDailyBar.trade_date <= end_date)
        row_count, symbol_count, first_trade_date, last_trade_date = self.db.execute(query).one()
        row_count = int(row_count or 0)
        symbol_count = int(symbol_count or 0)

        present_symbols: set[str] = set()
        if symbols:
            present_query = select(MarketDailyBar.symbol).where(MarketDailyBar.source == source, MarketDailyBar.adjustflag == adjustflag, MarketDailyBar.symbol.in_(symbols)).distinct()
            if start_date is not None:
                present_query = present_query.where(MarketDailyBar.trade_date >= start_date)
            if end_date is not None:
                present_query = present_query.where(MarketDailyBar.trade_date <= end_date)
            present_symbols = set(self.db.scalars(present_query).all())
        missing_symbols = [symbol for symbol in symbols if symbol not in present_symbols]

        expected_symbol_count = len(symbols) if symbols else symbol_count
        coverage_ratio = 1.0 if expected_symbol_count == 0 and row_count > 0 else 0.0 if expected_symbol_count == 0 else symbol_count / expected_symbol_count
        empty_ratio = 1.0 if row_count == 0 else 0.0
        field_missing_ratio = self._field_missing_ratio(
            source=source,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            adjustflag=adjustflag,
        ) if row_count else 1.0

        notes: list[str] = []
        staleness_days = None
        freshness_score = 0.0 if row_count == 0 else 1.0
        if last_trade_date is not None:
            reference_date = end_date or date.today()
            staleness_days = max((reference_date - last_trade_date).days, 0)
            freshness_score = max(0.0, 1 - (staleness_days / max(stale_after_days, 1)))
            if staleness_days > stale_after_days:
                notes.append(f"latest bar is {staleness_days} days behind reference date")
        if missing_symbols:
            notes.append(f"missing {len(missing_symbols)} requested symbols")
        if field_missing_ratio > 0:
            notes.append(f"nullable field missing ratio {field_missing_ratio:.2%}")
        if not row_count:
            status = "empty"
            notes.append("no local daily bars for this source")
        elif missing_symbols or (staleness_days is not None and staleness_days > stale_after_days):
            status = "partial"
        else:
            status = "healthy"
        health_level = {"healthy": "healthy", "partial": "degraded", "empty": "down"}[status]

        return MarketSourceHealthItem(
            source=source,
            label=SOURCE_LABELS.get(source, source),
            status=status,
            role="unavailable",
            symbol_count=symbol_count,
            row_count=row_count,
            first_trade_date=first_trade_date.isoformat() if first_trade_date else None,
            last_trade_date=last_trade_date.isoformat() if last_trade_date else None,
            missing_symbols=missing_symbols,
            staleness_days=staleness_days,
            health_level=health_level,
            coverage_ratio=round(coverage_ratio, 6),
            empty_ratio=round(empty_ratio, 6),
            field_missing_ratio=round(field_missing_ratio, 6),
            freshness_score=round(freshness_score, 6),
            notes=notes,
        )

    def _field_missing_ratio(
        self,
        *,
        source: str,
        symbols: list[str],
        start_date: date | None,
        end_date: date | None,
        adjustflag: str,
    ) -> float:
        nullable_fields = [
            MarketDailyBar.amplitude_pct,
            MarketDailyBar.change_pct,
            MarketDailyBar.turnover_rate,
            MarketDailyBar.preclose,
            MarketDailyBar.trade_status,
            MarketDailyBar.pe_ttm,
            MarketDailyBar.pb_mrq,
            MarketDailyBar.ps_ttm,
            MarketDailyBar.pcf_ncf_ttm,
            MarketDailyBar.is_st,
        ]
        query = select(
            func.count(MarketDailyBar.id),
            *[func.sum(field.is_(None).cast(Integer)) for field in nullable_fields],
        ).where(MarketDailyBar.source == source, MarketDailyBar.adjustflag == adjustflag)
        if symbols:
            query = query.where(MarketDailyBar.symbol.in_(symbols))
        if start_date is not None:
            query = query.where(MarketDailyBar.trade_date >= start_date)
        if end_date is not None:
            query = query.where(MarketDailyBar.trade_date <= end_date)
        row = self.db.execute(query).one()
        total_rows = int(row[0] or 0)
        if total_rows == 0:
            return 1.0
        missing_fields = sum(int(value or 0) for value in row[1:])
        return missing_fields / (total_rows * len(nullable_fields))

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            item = normalize_a_share_symbol(symbol)
            if item and item not in seen:
                seen.add(item)
                normalized.append(item)
        return normalized

    @staticmethod
    def _normalize_sources(sources: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for source in sources:
            item = source.strip().lower()
            if item and item not in seen:
                seen.add(item)
                normalized.append(item)
        return normalized or list(DEFAULT_HISTORY_SOURCE_PRIORITY)
