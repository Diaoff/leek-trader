from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import redis

from app.core.config import settings
from app.market.providers.base import QuoteProvider, QuoteSnapshot
from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.providers.sina import SinaQuoteProvider
from app.schemas.quote import QuoteRead

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MemoryQuoteCacheEntry:
    expires_at: float
    snapshots: list[QuoteSnapshot]


class QuoteCache:
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
        self._memory: dict[tuple[str, ...], MemoryQuoteCacheEntry] = {}
        self._lock = threading.Lock()
        self._redis_unavailable = False

    def get(self, symbols: list[str], *, allow_stale: bool = False) -> list[QuoteSnapshot] | None:
        key = self._cache_key(symbols)
        entry = self._get_from_memory(key, allow_stale=allow_stale)
        if entry is not None:
            return entry

        payload = self._get_from_redis(key)
        if payload is None:
            return None

        snapshots = self._deserialize(payload)
        self._set_memory(key, snapshots)
        return snapshots

    def set(self, symbols: list[str], snapshots: list[QuoteSnapshot]) -> None:
        key = self._cache_key(symbols)
        self._set_memory(key, snapshots)
        self._set_redis(key, self._serialize(snapshots))

    def invalidate(self, symbols: list[str] | None = None) -> None:
        if symbols is None:
            with self._lock:
                self._memory.clear()
            return

        key = self._cache_key(symbols)
        with self._lock:
            self._memory.pop(key, None)

    def _get_from_memory(self, key: tuple[str, ...], *, allow_stale: bool) -> list[QuoteSnapshot] | None:
        with self._lock:
            entry = self._memory.get(key)
            if entry is None:
                return None
            if allow_stale or entry.expires_at > self.time_fn():
                return list(entry.snapshots)
            return None

    def _set_memory(self, key: tuple[str, ...], snapshots: list[QuoteSnapshot]) -> None:
        with self._lock:
            self._memory[key] = MemoryQuoteCacheEntry(
                expires_at=self.time_fn() + self.ttl_seconds,
                snapshots=list(snapshots),
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
            logger.warning("Quote cache redis client init failed: %s", error)
            self._redis_unavailable = True
            return None
        return self.redis_client

    def _get_from_redis(self, key: tuple[str, ...]) -> str | None:
        client = self._get_redis_client()
        if client is None:
            return None
        try:
            return client.get(self._redis_key(key))
        except Exception as error:
            logger.warning("Quote cache redis get failed: %s", error)
            self._redis_unavailable = True
            return None

    def _set_redis(self, key: tuple[str, ...], payload: str) -> None:
        client = self._get_redis_client()
        if client is None:
            return
        try:
            client.setex(self._redis_key(key), self.ttl_seconds, payload)
        except Exception as error:
            logger.warning("Quote cache redis set failed: %s", error)
            self._redis_unavailable = True

    @staticmethod
    def _cache_key(symbols: list[str]) -> tuple[str, ...]:
        return tuple(symbols)

    @staticmethod
    def _redis_key(key: tuple[str, ...]) -> str:
        return f"quotes:{','.join(key)}"

    @staticmethod
    def _serialize(snapshots: list[QuoteSnapshot]) -> str:
        return json.dumps(
            [
                {
                    "symbol": snapshot.symbol,
                    "price": snapshot.price,
                    "change_percent": snapshot.change_percent,
                    "volume": snapshot.volume,
                    "timestamp": snapshot.timestamp.isoformat(),
                    "is_halted": snapshot.is_halted,
                    "market_cap": snapshot.market_cap,
                    "ytd_change_percent": snapshot.ytd_change_percent,
                }
                for snapshot in snapshots
            ]
        )

    @staticmethod
    def _deserialize(payload: str) -> list[QuoteSnapshot]:
        items = json.loads(payload)
        return [
            QuoteSnapshot(
                symbol=item["symbol"],
                price=float(item["price"]),
                change_percent=float(item["change_percent"]),
                volume=float(item["volume"]),
                timestamp=datetime.fromisoformat(item["timestamp"]),
                is_halted=bool(item.get("is_halted", False)),
                market_cap=float(item["market_cap"]) if item.get("market_cap") is not None else None,
                ytd_change_percent=float(item["ytd_change_percent"]) if item.get("ytd_change_percent") is not None else None,
            )
            for item in items
        ]


_shared_quote_cache = QuoteCache(
    ttl_seconds=settings.quote_cache_ttl_seconds,
    redis_url=settings.redis_url,
)


class QuoteService:
    def __init__(
        self,
        providers: list[QuoteProvider] | None = None,
        cache: QuoteCache | None = None,
    ) -> None:
        self.providers = providers or [
            EastMoneyQuoteProvider(),
            SinaQuoteProvider(),
        ]
        self.cache = cache or _shared_quote_cache

    def list_quotes(self, symbols: list[str], *, force_refresh: bool = False) -> list[QuoteRead]:
        normalized_symbols = self._normalize_symbols(symbols)
        if not normalized_symbols:
            return []
        snapshots = self._normalize_snapshots(self._load_snapshots(normalized_symbols, force_refresh=force_refresh))
        return [self._to_read_model(item) for item in snapshots]

    def refresh_quotes(self, symbols: list[str] | None = None) -> list[QuoteRead]:
        target_symbols = settings.market_refresh_symbol_list if symbols is None else symbols
        return self.list_quotes(target_symbols, force_refresh=True)

    def _load_snapshots(self, symbols: list[str], *, force_refresh: bool) -> list[QuoteSnapshot]:
        if not force_refresh:
            cached = self.cache.get(symbols)
            if cached is not None:
                logger.debug("Quote cache hit for symbols=%s", symbols)
                return cached

        snapshots = self._fetch_with_fallback(symbols)
        if snapshots:
            self.cache.set(symbols, snapshots)
            return snapshots

        stale = self.cache.get(symbols, allow_stale=True)
        if stale is not None:
            logger.warning("Quote providers failed, returning stale cached quotes for symbols=%s", symbols)
            return stale
        return []

    def _fetch_with_fallback(self, symbols: list[str]) -> list[QuoteSnapshot]:
        for provider in self.providers:
            try:
                snapshots = provider.fetch_quotes(symbols)
            except Exception as error:
                logger.warning("Quote provider %s failed: %s", provider.name, error)
                continue
            if snapshots:
                return snapshots
        return []

    @classmethod
    def _normalize_snapshots(cls, snapshots: list[QuoteSnapshot]) -> list[QuoteSnapshot]:
        for snapshot in snapshots:
            snapshot.change_percent = cls._normalize_change_percent(snapshot.change_percent)
        return snapshots

    @staticmethod
    def _normalize_change_percent(value: float) -> float:
        # Some quote sources occasionally return basis points like -329 for -3.29%.
        return round(value / 100, 2) if abs(value) > 100 else value

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized_symbol = symbol.strip().lower()
            if not normalized_symbol or normalized_symbol in seen:
                continue
            seen.add(normalized_symbol)
            normalized.append(normalized_symbol)
        return normalized

    @staticmethod
    def _to_read_model(item: QuoteSnapshot) -> QuoteRead:
        return QuoteRead(
            symbol=item.symbol,
            price=item.price,
            change_percent=item.change_percent,
            volume=item.volume,
            timestamp=item.timestamp.isoformat(),
            is_halted=item.is_halted,
            market_cap=item.market_cap,
            ytd_change_percent=item.ytd_change_percent,
        )
