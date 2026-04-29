from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable

import redis

from app.core.config import settings
from app.market.providers.base import DailyBarSnapshot, PriceHistoryProvider, QuoteSnapshot
from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.providers.sina import SinaDailyBarProvider
from app.market.providers.tencent import TencentDailyBarProvider
from app.market.service import QuoteService
from app.market.symbols import normalize_a_share_symbol

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    "eastmoney": "东方财富前复权日线",
    "sina": "新浪日线",
    "tencent": "腾讯前复权日线",
}

MIN_DAILY_BARS_FOR_TECH_ANALYSIS = 30


@dataclass(slots=True)
class DailyBarsPayload:
    bars: list[DailyBarSnapshot]
    source: str = "none"


@dataclass(slots=True)
class MemoryHistoryCacheEntry:
    expires_at: float
    payload: DailyBarsPayload


class DailyBarCache:
    def __init__(
        self,
        *,
        ttl_seconds: int,
        redis_url: str | None = None,
        time_fn: Callable[[], float] | None = None,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.redis_url = redis_url
        self.time_fn = time_fn or time.time
        self.redis_client = redis_client
        self._memory: dict[tuple[str, int], MemoryHistoryCacheEntry] = {}
        self._lock = threading.Lock()
        self._redis_unavailable = False

    def get(self, symbol: str, limit: int) -> DailyBarsPayload | None:
        key = self._cache_key(symbol, limit)
        entry = self._get_from_memory(key)
        if entry is not None:
            return entry

        payload = self._get_from_redis(key)
        if payload is None:
            return None

        bars_payload = self._deserialize(payload)
        self._set_memory(key, bars_payload)
        return bars_payload

    def set(self, symbol: str, limit: int, payload: DailyBarsPayload) -> None:
        key = self._cache_key(symbol, limit)
        self._set_memory(key, payload)
        self._set_redis(key, self._serialize(payload))

    def invalidate(self, symbol: str | None = None, limit: int | None = None) -> None:
        with self._lock:
            if symbol is None:
                self._memory.clear()
                return
            normalized_symbol = normalize_a_share_symbol(symbol)
            keys = [key for key in self._memory if key[0] == normalized_symbol and (limit is None or key[1] == limit)]
            for key in keys:
                self._memory.pop(key, None)

    def _get_from_memory(self, key: tuple[str, int]) -> DailyBarsPayload | None:
        with self._lock:
            entry = self._memory.get(key)
            if entry is None or entry.expires_at <= self.time_fn():
                return None
            return DailyBarsPayload(bars=list(entry.payload.bars), source=entry.payload.source)

    def _set_memory(self, key: tuple[str, int], payload: DailyBarsPayload) -> None:
        with self._lock:
            self._memory[key] = MemoryHistoryCacheEntry(
                expires_at=self.time_fn() + self.ttl_seconds,
                payload=DailyBarsPayload(bars=list(payload.bars), source=payload.source),
            )

    def _get_redis_client(self) -> redis.Redis | None:
        if self.redis_client is not None:
            return self.redis_client
        if self._redis_unavailable or not self.redis_url:
            return None
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=0.2,
                socket_connect_timeout=0.2,
            )
        except Exception as error:  # pragma: no cover - defensive path
            logger.warning("History cache redis client init failed: %s", error)
            self._redis_unavailable = True
            return None
        return self.redis_client

    def _get_from_redis(self, key: tuple[str, int]) -> str | None:
        client = self._get_redis_client()
        if client is None:
            return None
        try:
            return client.get(self._redis_key(key))
        except Exception as error:
            logger.warning("History cache redis get failed: %s", error)
            self._redis_unavailable = True
            return None

    def _set_redis(self, key: tuple[str, int], payload: str) -> None:
        client = self._get_redis_client()
        if client is None:
            return
        try:
            client.setex(self._redis_key(key), self.ttl_seconds, payload)
        except Exception as error:
            logger.warning("History cache redis set failed: %s", error)
            self._redis_unavailable = True

    @staticmethod
    def _cache_key(symbol: str, limit: int) -> tuple[str, int]:
        return normalize_a_share_symbol(symbol), limit

    @staticmethod
    def _redis_key(key: tuple[str, int]) -> str:
        symbol, limit = key
        return f"market:history:{symbol}:{limit}"

    @staticmethod
    def _serialize(payload: DailyBarsPayload) -> str:
        return json.dumps(
            {
                "source": payload.source,
                "bars": [
                    {
                        "symbol": bar.symbol,
                        "trade_date": bar.trade_date.isoformat(),
                        "open_price": bar.open_price,
                        "close_price": bar.close_price,
                        "high_price": bar.high_price,
                        "low_price": bar.low_price,
                        "volume": bar.volume,
                        "turnover": bar.turnover,
                        "amplitude_pct": bar.amplitude_pct,
                        "change_pct": bar.change_pct,
                        "turnover_rate": bar.turnover_rate,
                    }
                    for bar in payload.bars
                ],
            }
        )

    @staticmethod
    def _deserialize(payload: str) -> DailyBarsPayload:
        item = json.loads(payload)
        return DailyBarsPayload(
            source=str(item.get("source") or "none"),
            bars=[
                DailyBarSnapshot(
                    symbol=str(bar["symbol"]),
                    trade_date=date.fromisoformat(str(bar["trade_date"])),
                    open_price=float(bar["open_price"]),
                    close_price=float(bar["close_price"]),
                    high_price=float(bar["high_price"]),
                    low_price=float(bar["low_price"]),
                    volume=float(bar["volume"]),
                    turnover=float(bar.get("turnover") or 0.0),
                    amplitude_pct=float(bar["amplitude_pct"]) if bar.get("amplitude_pct") is not None else None,
                    change_pct=float(bar["change_pct"]) if bar.get("change_pct") is not None else None,
                    turnover_rate=float(bar["turnover_rate"]) if bar.get("turnover_rate") is not None else None,
                )
                for bar in item.get("bars", [])
            ],
        )


_shared_history_cache = DailyBarCache(
    ttl_seconds=settings.market_history_cache_ttl_seconds,
    redis_url=settings.redis_url,
)


class MarketDataService:
    def __init__(
        self,
        *,
        quote_service: QuoteService | None = None,
        history_providers: list[PriceHistoryProvider] | None = None,
        history_cache: DailyBarCache | None = None,
    ) -> None:
        self.quote_service = quote_service or QuoteService()
        self.history_providers = history_providers or [
            EastMoneyQuoteProvider(),
            SinaDailyBarProvider(),
            TencentDailyBarProvider(),
        ]
        self.history_cache = history_cache or _shared_history_cache

    @property
    def providers(self) -> list[PriceHistoryProvider]:
        return self.history_providers

    @providers.setter
    def providers(self, providers: list[PriceHistoryProvider]) -> None:
        self.history_providers = providers
        self.history_cache.invalidate()

    def get_quotes(self, symbols: list[str], *, force_refresh: bool = False) -> list[QuoteSnapshot]:
        normalized_symbols = self._normalize_symbols(symbols)
        if not normalized_symbols:
            return []
        snapshots = self.quote_service._load_snapshots(normalized_symbols, force_refresh=force_refresh)
        return self.quote_service._normalize_snapshots(snapshots)

    def get_daily_bars(self, symbol: str, limit: int = 60, *, force_refresh: bool = False) -> list[DailyBarSnapshot]:
        return self._load_daily_bars(symbol, limit=limit, force_refresh=force_refresh).bars

    def get_daily_bars_csv(self, symbol: str, limit: int = 60, *, force_refresh: bool = False) -> str:
        payload = self._load_daily_bars(symbol, limit=limit, force_refresh=force_refresh)
        return self._daily_bars_to_csv(payload.bars)

    def get_daily_bars_csv_with_source(
        self,
        symbol: str,
        limit: int = 60,
        *,
        force_refresh: bool = False,
    ) -> tuple[str, str]:
        payload = self._load_daily_bars(symbol, limit=limit, force_refresh=force_refresh)
        csv = self._daily_bars_to_csv(payload.bars)
        if not csv:
            return "", "none"
        return csv, SOURCE_LABELS.get(payload.source, payload.source or "none")

    def _load_daily_bars(self, symbol: str, *, limit: int, force_refresh: bool) -> DailyBarsPayload:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol:
            return DailyBarsPayload(bars=[], source="none")

        if not force_refresh:
            cached = self.history_cache.get(normalized_symbol, limit)
            if cached is not None:
                logger.debug("History cache hit for symbol=%s limit=%s", normalized_symbol, limit)
                return cached

        payload = self._fetch_daily_bars_with_fallback(normalized_symbol, limit)
        if payload.bars:
            self.history_cache.set(normalized_symbol, limit, payload)
        return payload

    def _fetch_daily_bars_with_fallback(self, symbol: str, limit: int) -> DailyBarsPayload:
        best_payload = DailyBarsPayload(bars=[], source="none")
        for provider in self.history_providers:
            try:
                bars = provider.fetch_daily_bars(symbol, limit=limit)
            except Exception as error:
                logger.warning("History provider %s failed for symbol=%s: %s", provider.name, symbol, error)
                continue
            normalized_bars = self._normalize_daily_bars(symbol, bars)
            if not normalized_bars:
                continue
            if len(normalized_bars) >= MIN_DAILY_BARS_FOR_TECH_ANALYSIS:
                return DailyBarsPayload(bars=normalized_bars, source=provider.name)
            if len(normalized_bars) > len(best_payload.bars):
                best_payload = DailyBarsPayload(bars=normalized_bars, source=provider.name)
        return best_payload

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

    @staticmethod
    def _normalize_daily_bars(symbol: str, bars: list[DailyBarSnapshot]) -> list[DailyBarSnapshot]:
        normalized_symbol = normalize_a_share_symbol(symbol)
        for bar in bars:
            bar.symbol = normalized_symbol
        return bars

    @staticmethod
    def _daily_bars_to_csv(bars: list[DailyBarSnapshot]) -> str:
        if not bars:
            return ""
        rows = ["日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率"]
        previous_close: float | None = None
        for bar in bars:
            change_amount = ""
            if previous_close is not None:
                change_amount = str(round(bar.close_price - previous_close, 4))
            rows.append(
                ",".join(
                    [
                        bar.trade_date.isoformat(),
                        str(bar.open_price),
                        str(bar.close_price),
                        str(bar.high_price),
                        str(bar.low_price),
                        str(bar.volume),
                        str(bar.turnover),
                        "" if bar.amplitude_pct is None else str(bar.amplitude_pct),
                        "" if bar.change_pct is None else str(bar.change_pct),
                        change_amount,
                        "" if bar.turnover_rate is None else str(bar.turnover_rate),
                    ]
                )
            )
            previous_close = bar.close_price
        return "\n".join(rows)
