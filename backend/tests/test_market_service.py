from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from app.market.history_service import HistoryService
from app.market.providers.base import DailyBarSnapshot, QuoteSnapshot
from app.market.providers.base import IntradayBarSnapshot
from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.providers.sina import SinaQuoteProvider
from app.market.providers.tencent import TencentDailyBarProvider
from app.market.service import QuoteCache, QuoteService


def build_snapshot(symbol: str = "sh600519", price: float = 123.45) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol,
        price=price,
        change_percent=1.23,
        volume=456789.0,
        timestamp=datetime(2026, 4, 21, 9, 30, 0, tzinfo=ZoneInfo("UTC")),
        is_halted=False,
        market_cap=2100000000000.0,
        ytd_change_percent=18.76,
    )


class FailingProvider:
    name = "failing"

    def fetch_quotes(self, symbols: list[str]):
        raise RuntimeError("primary provider failed")


class StubProvider:
    name = "stub"

    def fetch_quotes(self, symbols: list[str]):
        return [build_snapshot(symbol=symbols[0])]


class CountingProvider:
    name = "counting"

    def __init__(self, price: float = 123.45) -> None:
        self.price = price
        self.call_count = 0

    def fetch_quotes(self, symbols: list[str]):
        self.call_count += 1
        return [build_snapshot(symbol=symbols[0], price=self.price)]


class BasisPointProvider:
    name = "basis-point"

    def fetch_quotes(self, symbols: list[str]):
        return [
            QuoteSnapshot(
                symbol=symbols[0],
                price=49.88,
                change_percent=-329.0,
                volume=123456.0,
                timestamp=datetime(2026, 4, 21, 9, 30, 0, tzinfo=ZoneInfo("UTC")),
                is_halted=False,
            )
        ]


class EmptyHistoryProvider:
    name = "empty-history"

    def __init__(self) -> None:
        self.symbols: list[str] = []

    def fetch_daily_bars(self, symbol: str, limit: int = 60):
        self.symbols.append(symbol)
        return []


class StubHistoryProvider:
    name = "stub-history"

    def __init__(self) -> None:
        self.symbols: list[str] = []

    def fetch_daily_bars(self, symbol: str, limit: int = 60):
        self.symbols.append(symbol)
        return [
            DailyBarSnapshot(
                symbol=symbol,
                trade_date=date(2026, 4, 21),
                open_price=10.0,
                close_price=10.5,
                high_price=10.8,
                low_price=9.9,
                volume=1000000.0,
            )
        ]


class ShortHistoryProvider(StubHistoryProvider):
    name = "short-history"

    def __init__(self, count: int) -> None:
        super().__init__()
        self.count = count

    def fetch_daily_bars(self, symbol: str, limit: int = 60):
        self.symbols.append(symbol)
        return [
            DailyBarSnapshot(
                symbol=symbol,
                trade_date=date(2026, 4, 1),
                open_price=10.0,
                close_price=10.5,
                high_price=10.8,
                low_price=9.9,
                volume=1000000.0,
            )
            for _ in range(self.count)
        ]


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        self.store[key] = value


def test_sina_provider_parse_response() -> None:
    provider = SinaQuoteProvider()
    payload = (
        'var hq_str_sh600519="贵州茅台,100.00,101.00,102.00,103.00,99.00,0,0,123456,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-04-21,09:30:00,00";'
    )

    quotes = provider.parse_response(payload)

    assert len(quotes) == 1
    assert quotes[0].symbol == "sh600519"
    assert quotes[0].price == 102.0
    assert quotes[0].change_percent == 0.99
    assert quotes[0].volume == 123456.0
    assert quotes[0].is_halted is False


def test_eastmoney_provider_parse_response() -> None:
    provider = EastMoneyQuoteProvider()
    payload = '{"data":{"diff":[{"f12":"600519","f13":1,"f2":123.45,"f3":2.34,"f6":456789.0,"f20":2100000000000.0}]}}'

    quotes = provider.parse_response(payload)

    assert len(quotes) == 1
    assert quotes[0].symbol == "sh600519"
    assert quotes[0].price == 123.45
    assert quotes[0].change_percent == 2.34
    assert quotes[0].volume == 456789.0
    assert quotes[0].is_halted is False
    assert quotes[0].market_cap == 2100000000000.0


def test_eastmoney_provider_parse_intraday_bars() -> None:
    provider = EastMoneyQuoteProvider()

    bars = provider.parse_intraday_bars(
        "sh600519",
        ["2026-05-07 09:35,100.0,101.0,102.0,99.5,1200,121000"],
        interval="5m",
    )

    assert len(bars) == 1
    assert bars[0].symbol == "sh600519"
    assert bars[0].interval == "5m"
    assert bars[0].bar_time.isoformat() == "2026-05-07T09:35:00"
    assert bars[0].close_price == 101.0
    assert bars[0].turnover == 121000.0


def test_eastmoney_provider_parse_intraday_skips_invalid_rows() -> None:
    provider = EastMoneyQuoteProvider()

    bars = provider.parse_intraday_bars("sh600519", ["bad,row", "2026-05-07 09:40,101,102,103,100,1300,132000"], interval="15m")

    assert len(bars) == 1
    assert bars[0].interval == "15m"


def test_market_intraday_storage_upserts_and_reads_sorted(db) -> None:
    from datetime import datetime

    from app.market.intraday_storage import MarketIntradayBarStorage

    storage = MarketIntradayBarStorage(db)
    bars = [
        IntradayBarSnapshot("SH600519", datetime(2026, 5, 7, 9, 40), "5m", 101, 102, 100, 101.5, 1300, 132000),
        IntradayBarSnapshot("SH600519", datetime(2026, 5, 7, 9, 35), "5m", 100, 101, 99, 100.5, 1200, 121000),
        IntradayBarSnapshot("SH600519", datetime(2026, 5, 7, 9, 35), "5m", 100, 101, 99, 100.5, 1200, 121000),
    ]

    assert storage.upsert_bars(bars) == 2
    assert storage.upsert_bars(bars) == 2

    result = storage.list_bars(symbol="sh600519", interval="5m", limit=10)

    assert result.symbol == "sh600519"
    assert [bar.bar_time.isoformat() for bar in result.bars] == ["2026-05-07T09:35:00", "2026-05-07T09:40:00"]


def test_quote_service_falls_back_to_next_provider() -> None:
    service = QuoteService(providers=[FailingProvider(), StubProvider()])

    result = service.list_quotes(["sh600519"])

    assert len(result) == 1
    assert result[0].symbol == "sh600519"
    assert result[0].price == 123.45
    assert result[0].market_cap == 2100000000000.0
    assert result[0].ytd_change_percent == 18.76


def test_quote_service_returns_empty_for_empty_symbols() -> None:
    provider = CountingProvider()
    service = QuoteService(providers=[provider])

    result = service.list_quotes([])

    assert result == []
    assert provider.call_count == 0


def test_provider_capability_api_returns_static_matrix(client) -> None:
    response = client.get("/api/v1/market/providers/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    provider_names = {provider["name"] for provider in payload["providers"]}
    assert {"baostock", "eastmoney", "sina", "tencent"}.issubset(provider_names)
    eastmoney = next(provider for provider in payload["providers"] if provider["name"] == "eastmoney")
    capability_names = {capability["name"] for capability in eastmoney["capabilities"] if capability["supported"]}
    assert {"quote", "daily_bar", "intraday_bar"}.issubset(capability_names)
    assert eastmoney["stable_for_backtest"] is True
    baostock = next(provider for provider in payload["providers"] if provider["name"] == "baostock")
    baostock_capabilities = {capability["name"] for capability in baostock["capabilities"] if capability["supported"]}
    assert "daily_bar" in baostock_capabilities
    assert baostock["stable_for_backtest"] is True


def test_quote_service_normalizes_basis_point_change_percent() -> None:
    cache = QuoteCache(ttl_seconds=15, redis_url=None)
    service = QuoteService(providers=[BasisPointProvider()], cache=cache)

    result = service.list_quotes(["sh600519"])

    assert result[0].change_percent == -3.29


def test_tencent_daily_bar_provider_parses_qfq_payload() -> None:
    payload = {
        "data": {
            "sh600519": {
                "qfqday": [
                    ["2026-04-20", "100.00", "101.00", "102.00", "99.00", "123456"],
                    ["2026-04-21", "101.00", "103.00", "104.00", "100.00", "234567"],
                ]
            }
        }
    }

    bars = TencentDailyBarProvider.parse_daily_bars("sh600519", payload)

    assert len(bars) == 2
    assert bars[0].trade_date == date(2026, 4, 20)
    assert bars[0].open_price == 100.0
    assert bars[1].close_price == 103.0
    assert bars[1].volume == 234567.0


def test_history_service_falls_back_to_next_provider_and_normalizes_symbol() -> None:
    primary = EmptyHistoryProvider()
    fallback = StubHistoryProvider()
    service = HistoryService(providers=[primary, fallback])

    result = service.get_daily_bars("301667.SZ", limit=60)

    assert len(result) == 1
    assert result[0].symbol == "sz301667"
    assert primary.symbols == ["sz301667"]
    assert fallback.symbols == ["sz301667"]


def test_quote_service_uses_ttl_cache_before_expiry() -> None:
    now = [100.0]
    provider = CountingProvider()
    cache = QuoteCache(ttl_seconds=15, redis_url=None, time_fn=lambda: now[0])
    service = QuoteService(providers=[provider], cache=cache)

    first = service.list_quotes(["sh600519"])
    second = service.list_quotes(["sh600519"])

    assert provider.call_count == 1
    assert first[0].price == second[0].price


def test_quote_service_refresh_quotes_forces_provider_fetch() -> None:
    now = [100.0]
    provider = CountingProvider(price=123.45)
    cache = QuoteCache(ttl_seconds=15, redis_url=None, time_fn=lambda: now[0])
    service = QuoteService(providers=[provider], cache=cache)

    first = service.list_quotes(["sh600519"])
    provider.price = 125.67
    refreshed = service.refresh_quotes(["sh600519"])

    assert provider.call_count == 2
    assert first[0].price == 123.45
    assert refreshed[0].price == 125.67


def test_quote_service_reads_warmed_cache_from_shared_redis() -> None:
    fake_redis = FakeRedis()
    cache_writer = QuoteCache(ttl_seconds=15, redis_client=fake_redis, redis_url="redis://unused")
    cache_reader = QuoteCache(ttl_seconds=15, redis_client=fake_redis, redis_url="redis://unused")
    writer_provider = CountingProvider(price=123.45)
    reader_provider = CountingProvider(price=999.99)

    writer_service = QuoteService(providers=[writer_provider], cache=cache_writer)
    reader_service = QuoteService(providers=[reader_provider], cache=cache_reader)

    writer_service.refresh_quotes(["sh600519"])
    result = reader_service.list_quotes(["sh600519"])

    assert writer_provider.call_count == 1
    assert reader_provider.call_count == 0
    assert result[0].price == 123.45


def test_quote_service_returns_stale_cache_when_refresh_fails() -> None:
    now = [100.0]
    provider = CountingProvider(price=123.45)
    cache = QuoteCache(ttl_seconds=15, redis_url=None, time_fn=lambda: now[0])
    service = QuoteService(providers=[provider], cache=cache)

    service.list_quotes(["sh600519"])
    service.providers = [FailingProvider()]
    now[0] = 200.0

    result = service.list_quotes(["sh600519"])

    assert result[0].price == 123.45


def test_quote_service_raw_loader_uses_stale_cache_when_refresh_fails() -> None:
    now = [100.0]
    provider = CountingProvider(price=123.45)
    cache = QuoteCache(ttl_seconds=15, redis_url=None, time_fn=lambda: now[0])
    service = QuoteService(providers=[provider], cache=cache)

    service.list_quotes(["sh600519"])
    service.providers = [FailingProvider()]
    now[0] = 200.0

    result = service._load_snapshots(["sh600519"], force_refresh=False)

    assert result[0].price == 123.45


def test_eastmoney_provider_get_ytd_change_percent(monkeypatch) -> None:
    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "data": {
                    "klines": [
                        "2026-01-02,100.00,120.00,121.00,99.00,100000,200000,0,20.0,20.0,1.0",
                        "2026-04-21,120.00,132.00,133.00,119.00,100000,200000,0,10.0,10.0,1.0",
                    ]
                }
            }

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, params: dict[str, str]) -> FakeResponse:
            assert params["secid"] == "1.600519"
            return FakeResponse()

    EastMoneyQuoteProvider._get_ytd_reference_close.cache_clear()
    monkeypatch.setattr("app.market.providers.eastmoney.httpx.Client", FakeClient)

    provider = EastMoneyQuoteProvider()
    ytd_change_percent = provider._get_ytd_change_percent("sh600519", 132.0)

    assert ytd_change_percent == 10.0


def test_sina_provider_fetch_quotes_uses_browser_headers(monkeypatch) -> None:
    captured: dict[str, object] = {}
    payload = (
        'var hq_str_sh600519="贵州茅台,100.00,101.00,102.00,103.00,99.00,0,0,123456,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-04-21,09:30:00,00";'
    ).encode("gb18030")

    class FakeResponse:
        content = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["headers"] = kwargs.get("headers")
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str) -> FakeResponse:
            captured["url"] = url
            return FakeResponse()

    monkeypatch.setattr("app.market.providers.sina.httpx.Client", FakeClient)

    provider = SinaQuoteProvider()
    quotes = provider.fetch_quotes(["sh600519"])

    assert captured["timeout"] == 5.0
    assert captured["url"] == "https://hq.sinajs.cn/list=sh600519"
    assert captured["headers"]["Referer"] == "http://finance.sina.com.cn/"
    assert "Mozilla/5.0" in captured["headers"]["User-Agent"]
    assert provider._decode_payload(payload).split('="')[1].split(",")[0] == "贵州茅台"
    assert quotes[0].symbol == "sh600519"
    assert quotes[0].price == 102.0
    assert quotes[0].change_percent == 0.99


def test_eastmoney_provider_fetch_quotes_uses_float_normalization_params(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        text = '{"data":{"diff":[{"f12":"300750","f13":0,"f2":214.20,"f3":-1.49,"f6":5515572390.19,"f20":1955251926835.0}]}}'

        @staticmethod
        def raise_for_status() -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, params: dict[str, str]) -> FakeResponse:
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

    monkeypatch.setattr("app.market.providers.eastmoney.httpx.Client", FakeClient)
    monkeypatch.setattr(EastMoneyQuoteProvider, "_get_ytd_change_percent", lambda self, symbol, latest_price: None)

    provider = EastMoneyQuoteProvider()
    quotes = provider.fetch_quotes(["sz300750"])

    assert quotes[0].symbol == "sz300750"
    assert quotes[0].price == 214.20
    assert quotes[0].change_percent == -1.49
    assert captured["url"] == provider.endpoint
    assert captured["params"]["fltt"] == "2"
    assert captured["params"]["invt"] == "2"


def test_quote_service_falls_back_after_sina_403() -> None:
    class ForbiddenSinaProvider:
        name = "sina"

        def fetch_quotes(self, symbols: list[str]):
            request = httpx.Request("GET", f"https://hq.sinajs.cn/list={','.join(symbols)}")
            response = httpx.Response(status_code=403, request=request)
            raise httpx.HTTPStatusError("403 Forbidden", request=request, response=response)

    service = QuoteService(providers=[ForbiddenSinaProvider(), StubProvider()])

    result = service.list_quotes(["sh600519"])

    assert len(result) == 1
    assert result[0].symbol == "sh600519"
    assert result[0].price == 123.45


def test_quote_service_returns_empty_when_all_providers_fail() -> None:
    class EmptyProvider:
        name = "empty"

        def fetch_quotes(self, symbols: list[str]):
            return []

    class BrokenProvider:
        name = "failing"

        def fetch_quotes(self, symbols: list[str]):
            raise RuntimeError("provider failed")

    service = QuoteService(
        providers=[EmptyProvider(), BrokenProvider()],
        cache=QuoteCache(ttl_seconds=15, redis_url=None),
    )

    result = service.list_quotes(["sh600519"])

    assert result == []


def test_market_data_service_history_falls_back_and_normalizes_symbol() -> None:
    from app.market.data_service import DailyBarCache, MarketDataService

    empty_provider = EmptyHistoryProvider()
    fallback_provider = StubHistoryProvider()
    service = MarketDataService(
        history_providers=[empty_provider, fallback_provider],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url=None),
    )

    bars = service.get_daily_bars("301667.SZ", limit=60)

    assert empty_provider.symbols == ["sz301667"]
    assert fallback_provider.symbols == ["sz301667"]
    assert bars[0].symbol == "sz301667"


def test_market_data_service_history_continues_fallback_when_bars_are_insufficient() -> None:
    from app.market.data_service import DailyBarCache, MarketDataService

    short_provider = ShortHistoryProvider(count=10)
    fallback_provider = ShortHistoryProvider(count=30)
    service = MarketDataService(
        history_providers=[short_provider, fallback_provider],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url=None),
    )

    bars = service.get_daily_bars("301667.SZ", limit=60)

    assert len(bars) == 30
    assert short_provider.symbols == ["sz301667"]
    assert fallback_provider.symbols == ["sz301667"]


def test_market_data_service_history_returns_best_short_payload_when_all_sources_are_insufficient() -> None:
    from app.market.data_service import DailyBarCache, MarketDataService

    shorter_provider = ShortHistoryProvider(count=8)
    short_provider = ShortHistoryProvider(count=12)
    service = MarketDataService(
        history_providers=[shorter_provider, short_provider],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url=None),
    )

    bars = service.get_daily_bars("301667.SZ", limit=60)

    assert len(bars) == 12
    assert shorter_provider.symbols == ["sz301667"]
    assert short_provider.symbols == ["sz301667"]


def test_market_data_service_history_cache_uses_normalized_key() -> None:
    from app.market.data_service import DailyBarCache, MarketDataService

    provider = StubHistoryProvider()
    service = MarketDataService(
        history_providers=[provider],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url=None),
    )

    first = service.get_daily_bars("301667.SZ", limit=60)
    second = service.get_daily_bars("301667", limit=60)
    third = service.get_daily_bars("sz301667", limit=60)

    assert len(provider.symbols) == 1
    assert first[0].symbol == "sz301667"
    assert second[0].symbol == "sz301667"
    assert third[0].symbol == "sz301667"


def test_market_data_service_history_redis_cache_hit_skips_provider() -> None:
    from app.market.data_service import DailyBarCache, MarketDataService

    redis_client = FakeRedis()
    writer_provider = StubHistoryProvider()
    writer = MarketDataService(
        history_providers=[writer_provider],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url="redis://example/0", redis_client=redis_client),
    )
    writer.get_daily_bars("301667.SZ", limit=60)

    reader_provider = StubHistoryProvider()
    reader = MarketDataService(
        history_providers=[reader_provider],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url="redis://example/0", redis_client=redis_client),
    )

    bars = reader.get_daily_bars("sz301667", limit=60)

    assert writer_provider.symbols == ["sz301667"]
    assert reader_provider.symbols == []
    assert bars[0].symbol == "sz301667"
    assert "market:history:sz301667:60" in redis_client.store


def test_market_data_service_history_cache_degrades_when_redis_fails() -> None:
    from app.market.data_service import DailyBarCache, MarketDataService

    class BrokenRedis:
        def get(self, key: str):
            raise RuntimeError("redis down")

        def setex(self, key: str, ttl_seconds: int, value: str) -> None:
            raise RuntimeError("redis down")

    provider = StubHistoryProvider()
    service = MarketDataService(
        history_providers=[provider],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url="redis://example/0", redis_client=BrokenRedis()),
    )

    bars = service.get_daily_bars("301667.SZ", limit=60)

    assert provider.symbols == ["sz301667"]
    assert bars[0].symbol == "sz301667"


def test_market_data_service_generates_ai_csv_from_canonical_bars() -> None:
    from app.market.data_service import DailyBarCache, MarketDataService

    service = MarketDataService(
        history_providers=[StubHistoryProvider()],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url=None),
    )

    csv, source = service.get_daily_bars_csv_with_source("301667.SZ", limit=60)

    assert source == "stub-history"
    assert csv.splitlines()[0] == "日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率"
    assert "2026-04-21,10.0,10.5,10.8,9.9,1000000.0" in csv


def test_baostock_provider_maps_symbols_and_rl_features() -> None:
    from app.market.providers.baostock import BAOSTOCK_FIELDS, BaoStockDailyBarProvider

    rows = [
        {
            "date": "2026-04-20",
            "code": "sh.600000",
            "open": "10.00",
            "high": "10.80",
            "low": "9.90",
            "close": "10.50",
            "preclose": "10.10",
            "volume": "1000000",
            "amount": "10500000",
            "adjustflag": "2",
            "turn": "1.23",
            "tradestatus": "1",
            "pctChg": "3.96",
            "peTTM": "12.3",
            "pbMRQ": "1.4",
            "psTTM": "2.5",
            "pcfNcfTTM": "8.9",
            "isST": "0",
        }
    ]

    bars = BaoStockDailyBarProvider.parse_daily_bars("600000.SH", rows)

    assert BaoStockDailyBarProvider.to_baostock_symbol("sz000001") == "sz.000001"
    assert BaoStockDailyBarProvider.to_baostock_symbol("600000.SH") == "sh.600000"
    assert "preclose" in BAOSTOCK_FIELDS
    assert "pcfNcfTTM" in BAOSTOCK_FIELDS
    assert len(bars) == 1
    assert bars[0].symbol == "sh600000"
    assert bars[0].preclose == 10.1
    assert bars[0].turnover_rate == 1.23
    assert bars[0].trade_status == 1
    assert bars[0].change_pct == 3.96
    assert bars[0].pe_ttm == 12.3
    assert bars[0].pb_mrq == 1.4
    assert bars[0].ps_ttm == 2.5
    assert bars[0].pcf_ncf_ttm == 8.9
    assert bars[0].is_st is False


def test_market_data_service_can_select_baostock_without_realtime_providers(monkeypatch) -> None:
    from app.market import data_service as data_service_module
    from app.market.data_service import DailyBarCache, MarketDataService

    class StubBaoStockProvider:
        name = "baostock"

        def fetch_daily_bars(self, symbol: str, limit: int = 60):
            return [
                DailyBarSnapshot(
                    symbol=symbol,
                    trade_date=date(2026, 4, 20),
                    open_price=10.0,
                    close_price=10.5,
                    high_price=10.8,
                    low_price=9.9,
                    volume=1000000.0,
                    preclose=10.1,
                    trade_status=1,
                    pe_ttm=12.3,
                )
            ]

    realtime_provider = StubHistoryProvider()
    monkeypatch.setattr(data_service_module, "BaoStockDailyBarProvider", StubBaoStockProvider)
    service = MarketDataService(
        history_providers=[realtime_provider],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url=None),
    )

    bars = service.get_daily_bars("000001.SZ", limit=60, source="baostock")

    assert realtime_provider.symbols == []
    assert bars[0].symbol == "sz000001"
    assert bars[0].preclose == 10.1
    assert bars[0].pe_ttm == 12.3


def test_market_data_service_source_specific_cache_does_not_shadow_default(monkeypatch) -> None:
    from app.market import data_service as data_service_module
    from app.market.data_service import DailyBarCache, MarketDataService

    class StubBaoStockProvider:
        name = "baostock"

        def fetch_daily_bars(self, symbol: str, limit: int = 60):
            return [
                DailyBarSnapshot(
                    symbol=symbol,
                    trade_date=date(2026, 4, 20),
                    open_price=20.0,
                    close_price=20.5,
                    high_price=20.8,
                    low_price=19.9,
                    volume=2000000.0,
                )
            ]

    monkeypatch.setattr(data_service_module, "BaoStockDailyBarProvider", StubBaoStockProvider)
    service = MarketDataService(
        history_providers=[StubHistoryProvider()],
        history_cache=DailyBarCache(ttl_seconds=3600, redis_url=None),
    )

    baostock_bars = service.get_daily_bars("301667.SZ", limit=60, source="baostock")
    default_bars = service.get_daily_bars("301667.SZ", limit=60)

    assert baostock_bars[0].close_price == 20.5
    assert default_bars[0].close_price == 10.5


def test_market_data_service_cache_preserves_rl_extension_fields() -> None:
    from app.market.data_service import DailyBarCache, DailyBarsPayload

    cache = DailyBarCache(ttl_seconds=3600, redis_url=None)
    cache.set(
        "600000.SH",
        60,
        DailyBarsPayload(
            source="baostock",
            bars=[
                DailyBarSnapshot(
                    symbol="sh600000",
                    trade_date=date(2026, 4, 20),
                    open_price=10.0,
                    close_price=10.5,
                    high_price=10.8,
                    low_price=9.9,
                    volume=1000000.0,
                    preclose=10.1,
                    trade_status=1,
                    pe_ttm=12.3,
                    pb_mrq=1.4,
                    ps_ttm=2.5,
                    pcf_ncf_ttm=8.9,
                    is_st=True,
                )
            ],
        ),
        source="baostock",
    )

    payload = cache.get("sh600000", 60, source="baostock")

    assert payload is not None
    assert payload.source == "baostock"
    assert payload.bars[0].preclose == 10.1
    assert payload.bars[0].trade_status == 1
    assert payload.bars[0].pcf_ncf_ttm == 8.9
    assert payload.bars[0].is_st is True
