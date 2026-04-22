from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.market.providers.base import QuoteSnapshot
from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.providers.sina import SinaQuoteProvider
from app.market.service import QuoteService


class FailingProvider:
    name = "failing"

    def fetch_quotes(self, symbols: list[str]):
        raise RuntimeError("primary provider failed")


class StubProvider:
    name = "stub"

    def fetch_quotes(self, symbols: list[str]):
        return [
            QuoteSnapshot(
                symbol=symbols[0],
                price=123.45,
                change_percent=1.23,
                volume=456789.0,
                timestamp=datetime(2026, 4, 21, 9, 30, 0, tzinfo=ZoneInfo("UTC")),
                is_halted=False,
            )
        ]


def test_sina_provider_parse_response() -> None:
    provider = SinaQuoteProvider()
    payload = (
        'var hq_str_sh600519="贵州茅台,100.00,101.00,102.00,103.00,99.00,0,0,123456,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-04-21,09:30:00,00";'
    )

    quotes = provider.parse_response(payload)

    assert len(quotes) == 1
    assert quotes[0].symbol == "sh600519"
    assert quotes[0].price == 102.0
    assert quotes[0].change_percent == 2.0
    assert quotes[0].volume == 123456.0
    assert quotes[0].is_halted is False


def test_eastmoney_provider_parse_response() -> None:
    provider = EastMoneyQuoteProvider()
    payload = '{"data":{"diff":[{"f12":"600519","f13":1,"f2":123.45,"f3":2.34,"f6":456789.0}]}}'

    quotes = provider.parse_response(payload)

    assert len(quotes) == 1
    assert quotes[0].symbol == "sh600519"
    assert quotes[0].price == 123.45
    assert quotes[0].change_percent == 2.34
    assert quotes[0].volume == 456789.0
    assert quotes[0].is_halted is False


def test_quote_service_falls_back_to_next_provider() -> None:
    service = QuoteService(providers=[FailingProvider(), StubProvider()])

    result = service.list_quotes(["sh600519"])

    assert len(result) == 1
    assert result[0].symbol == "sh600519"
    assert result[0].price == 123.45


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
