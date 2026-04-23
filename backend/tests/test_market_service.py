from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.market.providers.base import QuoteSnapshot
from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.providers.sina import SinaQuoteProvider
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


def test_quote_service_falls_back_to_next_provider() -> None:
    service = QuoteService(providers=[FailingProvider(), StubProvider()])

    result = service.list_quotes(["sh600519"])

    assert len(result) == 1
    assert result[0].symbol == "sh600519"
    assert result[0].price == 123.45
    assert result[0].market_cap == 2100000000000.0
    assert result[0].ytd_change_percent == 18.76


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
