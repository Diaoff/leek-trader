from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.market.providers.base import (
    MarketBreadthDistributionSnapshot,
    MarketOverviewProvider,
    MarketOverviewSnapshot,
    MarketSymbolSnapshot,
    MarketTurnoverSnapshot,
)
from app.market.providers.eastmoney_overview import EastMoneyOverviewProvider
from app.market.providers.sina_overview import SinaOverviewProvider
from app.schemas.market import (
    MarketBreadthBucketRead,
    MarketBreadthDistributionRead,
    MarketLimitStatsRead,
    MarketOverviewRead,
    MarketQuoteRead,
    MarketSentimentRead,
    MarketTurnoverSummaryRead,
    NorthboundSummaryRead,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MemoryOverviewCacheEntry:
    expires_at: float
    snapshot: MarketOverviewSnapshot


class MarketOverviewCache:
    def __init__(self, *, ttl_seconds: int, time_fn=time.time) -> None:
        self.ttl_seconds = ttl_seconds
        self.time_fn = time_fn
        self._entry: MemoryOverviewCacheEntry | None = None
        self._lock = threading.Lock()

    def get(self) -> MarketOverviewSnapshot | None:
        with self._lock:
            if self._entry is None or self._entry.expires_at <= self.time_fn():
                return None
            return self._entry.snapshot

    def get_stale(self) -> MarketOverviewSnapshot | None:
        with self._lock:
            return self._entry.snapshot if self._entry is not None else None

    def set(self, snapshot: MarketOverviewSnapshot) -> None:
        with self._lock:
            self._entry = MemoryOverviewCacheEntry(
                expires_at=self.time_fn() + self.ttl_seconds,
                snapshot=snapshot,
            )

    def invalidate(self) -> None:
        with self._lock:
            self._entry = None


_shared_market_overview_cache = MarketOverviewCache(ttl_seconds=settings.quote_cache_ttl_seconds)


class MarketOverviewService:
    def __init__(
        self,
        providers: list[MarketOverviewProvider] | None = None,
        cache: MarketOverviewCache | None = None,
    ) -> None:
        self.providers = providers or [EastMoneyOverviewProvider(), SinaOverviewProvider()]
        self.cache = cache or _shared_market_overview_cache

    def get_overview(self, *, force_refresh: bool = False) -> MarketOverviewRead:
        snapshot = self._load_snapshot(force_refresh=force_refresh)
        return self._to_read_model(snapshot)

    def _load_snapshot(self, *, force_refresh: bool) -> MarketOverviewSnapshot:
        cached_snapshot = self.cache.get_stale()
        if not force_refresh:
            cached = self.cache.get()
            if cached is not None:
                return cached

        merged: MarketOverviewSnapshot | None = None
        for provider in self.providers:
            try:
                snapshot = provider.fetch_overview()
            except Exception as error:
                logger.warning("Market overview provider %s failed: %s", provider.name, error)
                continue

            merged = snapshot if merged is None else self._merge_snapshots(merged, snapshot)

        if merged is not None and cached_snapshot is not None:
            merged = self._merge_snapshots(merged, cached_snapshot)

        if merged is not None and self._has_meaningful_data(merged):
            self.cache.set(merged)
            return merged

        logger.warning("All market overview providers failed, returning empty overview")
        empty = self._empty_snapshot()
        self.cache.set(empty)
        return empty

    @staticmethod
    def _empty_snapshot() -> MarketOverviewSnapshot:
        return MarketOverviewSnapshot(
            generated_at=datetime.now(UTC),
            source="none",
            northbound_net_inflow=None,
        )

    @staticmethod
    def _to_read_model(snapshot: MarketOverviewSnapshot) -> MarketOverviewRead:
        source = snapshot.source if snapshot.source != "none" else "none"
        return MarketOverviewRead(
            generated_at=snapshot.generated_at.isoformat(),
            indices=[MarketOverviewService._to_quote_read(item) for item in snapshot.indices],
            top_gainers=[MarketOverviewService._to_quote_read(item) for item in snapshot.top_gainers],
            top_losers=[MarketOverviewService._to_quote_read(item) for item in snapshot.top_losers],
            limit_up=MarketLimitStatsRead(
                total=snapshot.limit_up_total,
                sample=[MarketOverviewService._to_quote_read(item) for item in snapshot.limit_up_sample],
                source=source,
            ),
            limit_down=MarketLimitStatsRead(
                total=snapshot.limit_down_total,
                sample=[MarketOverviewService._to_quote_read(item) for item in snapshot.limit_down_sample],
                source=source,
            ),
            northbound=NorthboundSummaryRead(
                net_inflow=snapshot.northbound_net_inflow,
                unit="CNY",
                source=source if snapshot.northbound_net_inflow is not None else "none",
            ),
            hot_stocks=[MarketOverviewService._to_quote_read(item) for item in snapshot.hot_stocks],
            market_sentiment=MarketOverviewService._build_market_sentiment(snapshot),
            breadth_distribution=MarketOverviewService._to_breadth_read(snapshot.breadth_distribution),
            turnover_summary=MarketOverviewService._to_turnover_read(snapshot.turnover),
        )

    @staticmethod
    def _to_quote_read(item: MarketSymbolSnapshot) -> MarketQuoteRead:
        return MarketQuoteRead(
            symbol=item.symbol,
            code=item.code,
            name=item.name,
            price=item.price,
            change_percent=item.change_percent,
            volume=item.volume,
            sector=item.sector,
        )

    @staticmethod
    def _merge_snapshots(primary: MarketOverviewSnapshot, secondary: MarketOverviewSnapshot) -> MarketOverviewSnapshot:
        merged_sources = list(dict.fromkeys([primary.source, secondary.source]))
        return MarketOverviewSnapshot(
            generated_at=max(primary.generated_at, secondary.generated_at),
            source="+".join(source for source in merged_sources if source and source != "none") or "none",
            indices=primary.indices or secondary.indices,
            top_gainers=primary.top_gainers or secondary.top_gainers,
            top_losers=primary.top_losers or secondary.top_losers,
            limit_up_total=primary.limit_up_total or secondary.limit_up_total,
            limit_up_sample=primary.limit_up_sample or secondary.limit_up_sample,
            limit_down_total=primary.limit_down_total or secondary.limit_down_total,
            limit_down_sample=primary.limit_down_sample or secondary.limit_down_sample,
            northbound_net_inflow=(
                primary.northbound_net_inflow
                if primary.northbound_net_inflow is not None
                else secondary.northbound_net_inflow
            ),
            hot_stocks=primary.hot_stocks or secondary.hot_stocks,
            breadth_distribution=primary.breadth_distribution or secondary.breadth_distribution,
            turnover=primary.turnover or secondary.turnover,
        )

    @staticmethod
    def _has_meaningful_data(snapshot: MarketOverviewSnapshot) -> bool:
        return any(
            [
                bool(snapshot.indices),
                bool(snapshot.top_gainers),
                bool(snapshot.top_losers),
                bool(snapshot.hot_stocks),
                snapshot.limit_up_total > 0,
                snapshot.limit_down_total > 0,
                snapshot.northbound_net_inflow is not None,
                snapshot.breadth_distribution is not None,
                snapshot.turnover is not None,
            ]
        )

    @staticmethod
    def _build_market_sentiment(snapshot: MarketOverviewSnapshot) -> MarketSentimentRead | None:
        distribution = snapshot.breadth_distribution
        if distribution is None:
            return None

        breadth_ratio = (distribution.advancing_count + 1) / (distribution.declining_count + 1)
        northbound = snapshot.northbound_net_inflow

        score = 50.0
        score += min(max((breadth_ratio - 1.0) * 15, -18), 18)
        score += min(snapshot.limit_up_total, 40) * 0.25
        score -= min(snapshot.limit_down_total, 40) * 0.35
        if northbound is not None:
            score += max(min(northbound / 100000000, 8), -8)
        score = round(min(max(score, 0.0), 100.0), 2)

        if score >= 62:
            label = "strong"
            title = "情绪偏强"
            selection_mode = "momentum"
        elif score <= 42:
            label = "weak"
            title = "情绪偏弱"
            selection_mode = "defensive"
        else:
            label = "range"
            title = "震荡分化"
            selection_mode = "balanced"

        summary = (
            f"上涨 {distribution.advancing_count} 家，平盘 {distribution.flat_count} 家，"
            f"下跌 {distribution.declining_count} 家，涨停 {snapshot.limit_up_total} 家，跌停 {snapshot.limit_down_total} 家。"
        )

        return MarketSentimentRead(
            label=label,
            title=title,
            score=score,
            selection_mode=selection_mode,
            advancing_count=distribution.advancing_count,
            declining_count=distribution.declining_count,
            flat_count=distribution.flat_count,
            limit_up_count=snapshot.limit_up_total,
            limit_down_count=snapshot.limit_down_total,
            northbound_net_inflow=northbound,
            summary=summary,
        )

    @staticmethod
    def _to_breadth_read(snapshot: MarketBreadthDistributionSnapshot | None) -> MarketBreadthDistributionRead | None:
        if snapshot is None:
            return None
        return MarketBreadthDistributionRead(
            advancing_count=snapshot.advancing_count,
            flat_count=snapshot.flat_count,
            declining_count=snapshot.declining_count,
            buckets=[
                MarketBreadthBucketRead(
                    key=item.key,
                    label=item.label,
                    count=item.count,
                    tone=item.tone,
                )
                for item in snapshot.buckets
            ],
            source=snapshot.source,
        )

    @staticmethod
    def _to_turnover_read(snapshot: MarketTurnoverSnapshot | None) -> MarketTurnoverSummaryRead | None:
        if snapshot is None:
            return None
        return MarketTurnoverSummaryRead(
            today_amount=snapshot.today_amount,
            previous_day_amount=snapshot.previous_day_amount,
            delta_amount=snapshot.delta_amount,
            estimated_full_day_amount=snapshot.estimated_full_day_amount,
            source=snapshot.source,
        )
