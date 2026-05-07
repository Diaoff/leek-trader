from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

import redis

from app.core.config import settings
from app.market.providers.base import DailyBarSnapshot, IntradayBarProvider, IntradayBarSnapshot, PriceHistoryProvider, QuoteSnapshot
from app.market.providers.baostock import BaoStockDailyBarProvider
from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.providers.sina import SinaDailyBarProvider
from app.market.providers.tencent import TencentDailyBarProvider
from app.market.service import QuoteService
from app.market.symbols import normalize_a_share_symbol

logger = logging.getLogger(__name__)


def date_time_from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)

SOURCE_LABELS = {
    "baostock": "BaoStock前复权历史日线",
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
class IntradayBarsPayload:
    bars: list[IntradayBarSnapshot]
    source: str = "none"


@dataclass(slots=True)
class MemoryHistoryCacheEntry:
    expires_at: float
    payload: DailyBarsPayload


@dataclass(slots=True)
class MemoryIntradayCacheEntry:
    expires_at: float
    payload: IntradayBarsPayload


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
        self._memory: dict[tuple[str, int, str], MemoryHistoryCacheEntry] = {}
        self._lock = threading.Lock()
        self._redis_unavailable = False

    def get(self, symbol: str, limit: int, *, source: str | None = None) -> DailyBarsPayload | None:
        key = self._cache_key(symbol, limit, source)
        entry = self._get_from_memory(key)
        if entry is not None:
            return entry

        payload = self._get_from_redis(key)
        if payload is None:
            return None

        bars_payload = self._deserialize(payload)
        self._set_memory(key, bars_payload)
        return bars_payload

    def set(self, symbol: str, limit: int, payload: DailyBarsPayload, *, source: str | None = None) -> None:
        key = self._cache_key(symbol, limit, source)
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

    def _get_from_memory(self, key: tuple[str, int, str]) -> DailyBarsPayload | None:
        with self._lock:
            entry = self._memory.get(key)
            if entry is None or entry.expires_at <= self.time_fn():
                return None
            return DailyBarsPayload(bars=list(entry.payload.bars), source=entry.payload.source)

    def _set_memory(self, key: tuple[str, int, str], payload: DailyBarsPayload) -> None:
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

    def _get_from_redis(self, key: tuple[str, int, str]) -> str | None:
        client = self._get_redis_client()
        if client is None:
            return None
        try:
            return client.get(self._redis_key(key))
        except Exception as error:
            logger.warning("History cache redis get failed: %s", error)
            self._redis_unavailable = True
            return None

    def _set_redis(self, key: tuple[str, int, str], payload: str) -> None:
        client = self._get_redis_client()
        if client is None:
            return
        try:
            client.setex(self._redis_key(key), self.ttl_seconds, payload)
        except Exception as error:
            logger.warning("History cache redis set failed: %s", error)
            self._redis_unavailable = True

    @staticmethod
    def _cache_key(symbol: str, limit: int, source: str | None = None) -> tuple[str, int, str]:
        return normalize_a_share_symbol(symbol), limit, source or "default"

    @staticmethod
    def _redis_key(key: tuple[str, int, str]) -> str:
        symbol, limit, source = key
        if source == "default":
            return f"market:history:{symbol}:{limit}"
        return f"market:history:{source}:{symbol}:{limit}"

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
                        "preclose": bar.preclose,
                        "trade_status": bar.trade_status,
                        "pe_ttm": bar.pe_ttm,
                        "pb_mrq": bar.pb_mrq,
                        "ps_ttm": bar.ps_ttm,
                        "pcf_ncf_ttm": bar.pcf_ncf_ttm,
                        "is_st": bar.is_st,
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
                    preclose=float(bar["preclose"]) if bar.get("preclose") is not None else None,
                    trade_status=int(bar["trade_status"]) if bar.get("trade_status") is not None else None,
                    pe_ttm=float(bar["pe_ttm"]) if bar.get("pe_ttm") is not None else None,
                    pb_mrq=float(bar["pb_mrq"]) if bar.get("pb_mrq") is not None else None,
                    ps_ttm=float(bar["ps_ttm"]) if bar.get("ps_ttm") is not None else None,
                    pcf_ncf_ttm=float(bar["pcf_ncf_ttm"]) if bar.get("pcf_ncf_ttm") is not None else None,
                    is_st=bool(bar["is_st"]) if bar.get("is_st") is not None else None,
                )
                for bar in item.get("bars", [])
            ],
        )


class IntradayBarCache:
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
        self._memory: dict[tuple[str, str, int], MemoryIntradayCacheEntry] = {}
        self._lock = threading.Lock()
        self._redis_unavailable = False

    def get(self, symbol: str, interval: str, limit: int) -> IntradayBarsPayload | None:
        key = self._cache_key(symbol, interval, limit)
        entry = self._get_from_memory(key)
        if entry is not None:
            return entry

        payload = self._get_from_redis(key)
        if payload is None:
            return None

        bars_payload = self._deserialize(payload)
        self._set_memory(key, bars_payload)
        return bars_payload

    def set(self, symbol: str, interval: str, limit: int, payload: IntradayBarsPayload) -> None:
        key = self._cache_key(symbol, interval, limit)
        self._set_memory(key, payload)
        self._set_redis(key, self._serialize(payload))

    def invalidate(self, symbol: str | None = None) -> None:
        with self._lock:
            if symbol is None:
                self._memory.clear()
                return
            normalized_symbol = normalize_a_share_symbol(symbol)
            for key in [key for key in self._memory if key[0] == normalized_symbol]:
                self._memory.pop(key, None)

    def _get_from_memory(self, key: tuple[str, str, int]) -> IntradayBarsPayload | None:
        with self._lock:
            entry = self._memory.get(key)
            if entry is None or entry.expires_at <= self.time_fn():
                return None
            return IntradayBarsPayload(bars=list(entry.payload.bars), source=entry.payload.source)

    def _set_memory(self, key: tuple[str, str, int], payload: IntradayBarsPayload) -> None:
        with self._lock:
            self._memory[key] = MemoryIntradayCacheEntry(
                expires_at=self.time_fn() + self.ttl_seconds,
                payload=IntradayBarsPayload(bars=list(payload.bars), source=payload.source),
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
            logger.warning("Intraday cache redis client init failed: %s", error)
            self._redis_unavailable = True
            return None
        return self.redis_client

    def _get_from_redis(self, key: tuple[str, str, int]) -> str | None:
        client = self._get_redis_client()
        if client is None:
            return None
        try:
            return client.get(self._redis_key(key))
        except Exception as error:
            logger.warning("Intraday cache redis get failed: %s", error)
            self._redis_unavailable = True
            return None

    def _set_redis(self, key: tuple[str, str, int], payload: str) -> None:
        client = self._get_redis_client()
        if client is None:
            return
        try:
            client.setex(self._redis_key(key), self.ttl_seconds, payload)
        except Exception as error:
            logger.warning("Intraday cache redis set failed: %s", error)
            self._redis_unavailable = True

    @staticmethod
    def _cache_key(symbol: str, interval: str, limit: int) -> tuple[str, str, int]:
        return normalize_a_share_symbol(symbol), interval, limit

    @staticmethod
    def _redis_key(key: tuple[str, str, int]) -> str:
        symbol, interval, limit = key
        return f"market:intraday:{symbol}:{interval}:{limit}"

    @staticmethod
    def _serialize(payload: IntradayBarsPayload) -> str:
        return json.dumps(
            {
                "source": payload.source,
                "bars": [
                    {
                        "symbol": bar.symbol,
                        "bar_time": bar.bar_time.isoformat(),
                        "interval": bar.interval,
                        "open_price": bar.open_price,
                        "high_price": bar.high_price,
                        "low_price": bar.low_price,
                        "close_price": bar.close_price,
                        "volume": bar.volume,
                        "turnover": bar.turnover,
                    }
                    for bar in payload.bars
                ],
            }
        )

    @staticmethod
    def _deserialize(payload: str) -> IntradayBarsPayload:
        item = json.loads(payload)
        return IntradayBarsPayload(
            source=str(item.get("source") or "none"),
            bars=[
                IntradayBarSnapshot(
                    symbol=str(bar["symbol"]),
                    bar_time=date_time_from_iso(str(bar["bar_time"])),
                    interval=str(bar["interval"]),
                    open_price=float(bar["open_price"]),
                    high_price=float(bar["high_price"]),
                    low_price=float(bar["low_price"]),
                    close_price=float(bar["close_price"]),
                    volume=float(bar["volume"]),
                    turnover=float(bar.get("turnover") or 0.0),
                )
                for bar in item.get("bars", [])
            ],
        )


_shared_history_cache = DailyBarCache(
    ttl_seconds=settings.market_history_cache_ttl_seconds,
    redis_url=settings.redis_url,
)

_shared_intraday_cache = IntradayBarCache(
    ttl_seconds=min(settings.market_history_cache_ttl_seconds, 60),
    redis_url=settings.redis_url,
)


class MarketDataService:
    def __init__(
        self,
        *,
        quote_service: QuoteService | None = None,
        history_providers: list[PriceHistoryProvider] | None = None,
        intraday_providers: list[IntradayBarProvider] | None = None,
        history_cache: DailyBarCache | None = None,
        intraday_cache: IntradayBarCache | None = None,
    ) -> None:
        self.quote_service = quote_service or QuoteService()
        self.history_providers = history_providers or [
            EastMoneyQuoteProvider(),
            SinaDailyBarProvider(),
            TencentDailyBarProvider(),
        ]
        self.intraday_providers = intraday_providers or [EastMoneyQuoteProvider()]
        self.history_cache = history_cache or _shared_history_cache
        self.intraday_cache = intraday_cache or _shared_intraday_cache

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

    def get_daily_bars(
        self,
        symbol: str,
        limit: int = 60,
        *,
        force_refresh: bool = False,
        source: str | None = None,
    ) -> list[DailyBarSnapshot]:
        return self._load_daily_bars(symbol, limit=limit, force_refresh=force_refresh, source=source).bars

    def get_daily_bars_with_source(
        self,
        symbol: str,
        limit: int = 60,
        *,
        force_refresh: bool = False,
        source: str | None = None,
    ) -> DailyBarsPayload:
        return self._load_daily_bars(symbol, limit=limit, force_refresh=force_refresh, source=source)

    def get_daily_bars_csv(
        self,
        symbol: str,
        limit: int = 60,
        *,
        force_refresh: bool = False,
        source: str | None = None,
    ) -> str:
        payload = self._load_daily_bars(symbol, limit=limit, force_refresh=force_refresh, source=source)
        return self._daily_bars_to_csv(payload.bars)

    def get_daily_bars_csv_with_source(
        self,
        symbol: str,
        limit: int = 60,
        *,
        force_refresh: bool = False,
        source: str | None = None,
    ) -> tuple[str, str]:
        payload = self._load_daily_bars(symbol, limit=limit, force_refresh=force_refresh, source=source)
        csv = self._daily_bars_to_csv(payload.bars)
        if not csv:
            return "", "none"
        return csv, SOURCE_LABELS.get(payload.source, payload.source or "none")

    def get_intraday_bars(
        self,
        symbol: str,
        interval: str = "5m",
        limit: int = 120,
        *,
        force_refresh: bool = False,
    ) -> list[IntradayBarSnapshot]:
        return self.get_intraday_bars_with_source(symbol, interval=interval, limit=limit, force_refresh=force_refresh).bars

    def get_intraday_bars_with_source(
        self,
        symbol: str,
        interval: str = "5m",
        limit: int = 120,
        *,
        force_refresh: bool = False,
    ) -> IntradayBarsPayload:
        normalized_symbol = normalize_a_share_symbol(symbol)
        normalized_interval = self._normalize_intraday_interval(interval)
        normalized_limit = min(max(int(limit), 1), 240)
        if not normalized_symbol:
            return IntradayBarsPayload(bars=[], source="none")

        if not force_refresh:
            cached = self.intraday_cache.get(normalized_symbol, normalized_interval, normalized_limit)
            if cached is not None:
                return cached

        for provider in self.intraday_providers:
            try:
                bars = provider.fetch_intraday_bars(normalized_symbol, interval=normalized_interval, limit=normalized_limit)
            except Exception as error:
                logger.warning("Intraday provider %s failed for symbol=%s: %s", provider.name, normalized_symbol, error)
                continue
            normalized_bars = self._normalize_intraday_bars(normalized_symbol, normalized_interval, bars)[-normalized_limit:]
            if not normalized_bars:
                continue
            payload = IntradayBarsPayload(bars=normalized_bars, source=provider.name)
            self.intraday_cache.set(normalized_symbol, normalized_interval, normalized_limit, payload)
            return payload
        return IntradayBarsPayload(bars=[], source="none")

    def _load_daily_bars(
        self,
        symbol: str,
        *,
        limit: int,
        force_refresh: bool,
        source: str | None = None,
    ) -> DailyBarsPayload:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol:
            return DailyBarsPayload(bars=[], source="none")

        normalized_source = self._normalize_source(source)

        if not force_refresh:
            cached = self.history_cache.get(normalized_symbol, limit, source=normalized_source)
            if cached is not None:
                logger.debug("History cache hit for symbol=%s limit=%s", normalized_symbol, limit)
                return cached

        payload = self._fetch_daily_bars(normalized_symbol, limit, source=normalized_source)
        if payload.bars:
            self.history_cache.set(normalized_symbol, limit, payload, source=normalized_source)
        return payload

    def _fetch_daily_bars(self, symbol: str, limit: int, *, source: str | None) -> DailyBarsPayload:
        if source == "baostock":
            return self._fetch_daily_bars_from_provider(symbol, limit, BaoStockDailyBarProvider())
        return self._fetch_daily_bars_with_fallback(symbol, limit)

    def _fetch_daily_bars_from_provider(
        self,
        symbol: str,
        limit: int,
        provider: PriceHistoryProvider,
    ) -> DailyBarsPayload:
        try:
            bars = provider.fetch_daily_bars(symbol, limit=limit)
        except Exception as error:
            logger.warning("History provider %s failed for symbol=%s: %s", provider.name, symbol, error)
            return DailyBarsPayload(bars=[], source=provider.name)
        return DailyBarsPayload(bars=self._normalize_daily_bars(symbol, bars), source=provider.name)

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
    def _normalize_source(source: str | None) -> str | None:
        if source is None:
            return None
        normalized_source = source.strip().lower()
        return normalized_source or None

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
    def _normalize_intraday_interval(interval: str) -> str:
        normalized = interval.strip().lower()
        if normalized in {"5", "5m", "m5"}:
            return "5m"
        if normalized in {"15", "15m", "m15"}:
            return "15m"
        raise ValueError("unsupported intraday interval")

    @staticmethod
    def _normalize_intraday_bars(symbol: str, interval: str, bars: list[IntradayBarSnapshot]) -> list[IntradayBarSnapshot]:
        normalized_symbol = normalize_a_share_symbol(symbol)
        for bar in bars:
            bar.symbol = normalized_symbol
            bar.interval = interval
        return sorted(bars, key=lambda bar: bar.bar_time)

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
