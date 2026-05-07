from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market.providers.base import IntradayBarSnapshot
from app.market.symbols import normalize_a_share_symbol
from app.models.market_intraday_bar import MarketIntradayBar


@dataclass(slots=True)
class IntradayReadResult:
    symbol: str | None
    source: str
    interval: str
    bars: list[IntradayBarSnapshot]


class MarketIntradayBarStorage:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_bars(self, bars: list[IntradayBarSnapshot], *, source: str = "eastmoney") -> int:
        if not bars:
            return 0

        changed = 0
        now = datetime.now(timezone.utc)
        seen_keys: set[tuple[str, str, datetime]] = set()
        for bar in bars:
            normalized_symbol = normalize_a_share_symbol(bar.symbol)
            if not normalized_symbol:
                continue
            key = (normalized_symbol, bar.interval, bar.bar_time)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            existing = self.db.scalar(
                select(MarketIntradayBar).where(
                    MarketIntradayBar.symbol == normalized_symbol,
                    MarketIntradayBar.interval == bar.interval,
                    MarketIntradayBar.bar_time == bar.bar_time,
                    MarketIntradayBar.source == source,
                )
            )
            if existing is None:
                existing = MarketIntradayBar(
                    symbol=normalized_symbol,
                    bar_time=bar.bar_time,
                    interval=bar.interval,
                    source=source,
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
        symbol: str,
        interval: str = "5m",
        source: str = "eastmoney",
        limit: int | None = None,
    ) -> IntradayReadResult:
        normalized_symbol = normalize_a_share_symbol(symbol)
        query = select(MarketIntradayBar).where(
            MarketIntradayBar.symbol == normalized_symbol,
            MarketIntradayBar.interval == interval,
            MarketIntradayBar.source == source,
        )
        query = query.order_by(MarketIntradayBar.bar_time.desc())
        if limit is not None:
            query = query.limit(limit)
        rows = sorted(self.db.scalars(query).all(), key=lambda row: row.bar_time)
        return IntradayReadResult(
            symbol=normalized_symbol,
            source=source,
            interval=interval,
            bars=[self._to_snapshot(row) for row in rows],
        )

    @staticmethod
    def _apply_snapshot(row: MarketIntradayBar, bar: IntradayBarSnapshot, now: datetime) -> None:
        row.open_price = bar.open_price
        row.high_price = bar.high_price
        row.low_price = bar.low_price
        row.close_price = bar.close_price
        row.volume = bar.volume
        row.turnover = bar.turnover
        row.updated_at = now

    @staticmethod
    def _to_snapshot(row: MarketIntradayBar) -> IntradayBarSnapshot:
        return IntradayBarSnapshot(
            symbol=row.symbol,
            bar_time=row.bar_time,
            interval=row.interval,
            open_price=row.open_price,
            high_price=row.high_price,
            low_price=row.low_price,
            close_price=row.close_price,
            volume=row.volume,
            turnover=row.turnover,
        )
