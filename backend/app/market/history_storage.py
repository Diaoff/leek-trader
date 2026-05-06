from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.market.providers.base import DailyBarSnapshot
from app.market.symbols import normalize_a_share_symbol
from app.models.market_daily_bar import MarketDailyBar


@dataclass(slots=True)
class HistoryReadResult:
    symbol: str | None
    source: str
    adjustflag: str
    bars: list[DailyBarSnapshot]


class MarketDailyBarStorage:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_bars(self, bars: list[DailyBarSnapshot], *, source: str = "baostock", adjustflag: str = "2") -> int:
        if not bars:
            return 0

        changed = 0
        now = datetime.now(timezone.utc)
        seen_keys: set[tuple[str, date]] = set()
        for bar in bars:
            normalized_symbol = normalize_a_share_symbol(bar.symbol)
            if not normalized_symbol:
                continue
            key = (normalized_symbol, bar.trade_date)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            existing = self.db.scalar(
                select(MarketDailyBar).where(
                    MarketDailyBar.symbol == normalized_symbol,
                    MarketDailyBar.trade_date == bar.trade_date,
                    MarketDailyBar.source == source,
                    MarketDailyBar.adjustflag == adjustflag,
                )
            )
            if existing is None:
                existing = MarketDailyBar(
                    symbol=normalized_symbol,
                    trade_date=bar.trade_date,
                    source=source,
                    adjustflag=adjustflag,
                    created_at=now,
                )
                self.db.add(existing)
            self._apply_snapshot(existing, bar, now)
            changed += 1
        self.db.commit()
        return changed

    def list_bars(
        self,
        *,
        symbol: str | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        latest: bool = False,
    ) -> HistoryReadResult:
        normalized_symbol = normalize_a_share_symbol(symbol) if symbol else None
        query = select(MarketDailyBar).where(
            MarketDailyBar.source == source,
            MarketDailyBar.adjustflag == adjustflag,
        )
        if normalized_symbol:
            query = query.where(MarketDailyBar.symbol == normalized_symbol)
        if start_date:
            query = query.where(MarketDailyBar.trade_date >= start_date)
        if end_date:
            query = query.where(MarketDailyBar.trade_date <= end_date)
        if latest and not normalized_symbol:
            raise ValueError("latest=True requires a single symbol to avoid cross-symbol global limits")
        if latest:
            query = query.order_by(MarketDailyBar.trade_date.desc())
        else:
            query = query.order_by(MarketDailyBar.symbol.asc(), MarketDailyBar.trade_date.asc())
        if limit is not None:
            query = query.limit(limit)
        rows = self.db.scalars(query).all()
        if latest:
            rows = sorted(rows, key=lambda row: row.trade_date)
        return HistoryReadResult(
            symbol=normalized_symbol,
            source=source,
            adjustflag=adjustflag,
            bars=[self._to_snapshot(row) for row in rows],
        )

    def latest_trade_date(self, *, symbol: str, source: str = "baostock", adjustflag: str = "2") -> date | None:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol:
            return None
        return self.db.scalar(
            select(func.max(MarketDailyBar.trade_date)).where(
                MarketDailyBar.symbol == normalized_symbol,
                MarketDailyBar.source == source,
                MarketDailyBar.adjustflag == adjustflag,
            )
        )

    @staticmethod
    def _apply_snapshot(row: MarketDailyBar, bar: DailyBarSnapshot, now: datetime) -> None:
        row.open_price = bar.open_price
        row.close_price = bar.close_price
        row.high_price = bar.high_price
        row.low_price = bar.low_price
        row.volume = bar.volume
        row.turnover = bar.turnover
        row.amplitude_pct = bar.amplitude_pct
        row.change_pct = bar.change_pct
        row.turnover_rate = bar.turnover_rate
        row.preclose = bar.preclose
        row.trade_status = bar.trade_status
        row.pe_ttm = bar.pe_ttm
        row.pb_mrq = bar.pb_mrq
        row.ps_ttm = bar.ps_ttm
        row.pcf_ncf_ttm = bar.pcf_ncf_ttm
        row.is_st = bar.is_st
        row.updated_at = now

    @staticmethod
    def _to_snapshot(row: MarketDailyBar) -> DailyBarSnapshot:
        return DailyBarSnapshot(
            symbol=row.symbol,
            trade_date=row.trade_date,
            open_price=row.open_price,
            close_price=row.close_price,
            high_price=row.high_price,
            low_price=row.low_price,
            volume=row.volume,
            turnover=row.turnover,
            amplitude_pct=row.amplitude_pct,
            change_pct=row.change_pct,
            turnover_rate=row.turnover_rate,
            preclose=row.preclose,
            trade_status=row.trade_status,
            pe_ttm=row.pe_ttm,
            pb_mrq=row.pb_mrq,
            ps_ttm=row.ps_ttm,
            pcf_ncf_ttm=row.pcf_ncf_ttm,
            is_st=row.is_st,
        )
