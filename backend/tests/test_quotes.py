from fastapi.testclient import TestClient

from app.main import app
from app.schemas.quote import QuoteRead


client = TestClient(app)


def test_list_quotes_returns_quote_payload(monkeypatch) -> None:
    import app.api.quotes as quotes_module

    class FakeQuoteService:
        def list_quotes(self, symbols: list[str]) -> list[QuoteRead]:
            return [
                QuoteRead(
                    symbol="sh600519",
                    price=1415.74,
                    change_percent=4.4,
                    volume=3039624544.0,
                    timestamp="2026-04-23T02:59:06.930705+00:00",
                    is_halted=False,
                )
            ]

    monkeypatch.setattr(quotes_module, "service", FakeQuoteService())

    response = client.get("/api/v1/quotes")

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "symbol": "sh600519",
            "name": None,
            "price": 1415.74,
            "change_percent": 4.4,
            "volume": 3039624544.0,
            "timestamp": "2026-04-23T02:59:06.930705+00:00",
            "is_halted": False,
            "market_cap": None,
            "ytd_change_percent": None,
        }
    ]


def test_list_quotes_uses_symbols_query_params(client, monkeypatch) -> None:
    import app.api.quotes as quotes_module

    captured: dict[str, list[str]] = {}

    class FakeQuoteService:
        def list_quotes(self, symbols: list[str]) -> list[QuoteRead]:
            captured["symbols"] = symbols
            return []

    monkeypatch.setattr(quotes_module, "service", FakeQuoteService())

    response = client.get("/api/v1/quotes", params=[("symbols", "sh600519"), ("symbols", "sz300750")])

    assert response.status_code == 200
    assert captured["symbols"] == ["sh600519", "sz300750"]


def test_list_quotes_accepts_legacy_bracket_array_query_params(client, monkeypatch) -> None:
    import app.api.quotes as quotes_module

    captured: dict[str, list[str]] = {}

    class FakeQuoteService:
        def list_quotes(self, symbols: list[str]) -> list[QuoteRead]:
            captured["symbols"] = symbols
            return []

    monkeypatch.setattr(quotes_module, "service", FakeQuoteService())

    response = client.get("/api/v1/quotes?symbols[]=sh600519&symbols[]=sz300750")

    assert response.status_code == 200
    assert captured["symbols"] == ["sh600519", "sz300750"]
