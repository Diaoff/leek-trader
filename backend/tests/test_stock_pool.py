from app.schemas.quote import QuoteRead


def test_security_screen_marks_watchlist_items(client, monkeypatch) -> None:
    client.post("/api/v1/watchlists", json={"symbol": "sh600519"})

    response = client.get("/api/v1/securities/screen", params={"market": "sh", "limit": 10})

    assert response.status_code == 200
    items = response.json()
    target = next(item for item in items if item["symbol"] == "sh600519")
    assert target["in_watchlist"] is True


def test_security_screen_filters_market_cap(client, monkeypatch) -> None:
    from app.api import securities

    class FakeQuoteService:
        def list_quotes(self, symbols: list[str]) -> list[QuoteRead]:
            market_caps = {
                "sh600519": 2_000_000_000_000,
                "sh600036": 900_000_000_000,
            }
            return [
                QuoteRead(
                    symbol=symbol,
                    name=symbol,
                    price=10,
                    change_percent=0,
                    volume=0,
                    timestamp="2026-05-09T09:30:00",
                    is_halted=False,
                    market_cap=market_caps.get(symbol, 10_000_000_000),
                )
                for symbol in symbols
            ]

    monkeypatch.setattr(securities, "quote_service", FakeQuoteService())

    response = client.get(
        "/api/v1/securities/screen",
        params={"market": "sh", "min_market_cap": 1_000_000_000_000, "limit": 10},
    )

    assert response.status_code == 200
    assert [item["symbol"] for item in response.json()] == ["sh600519"]
    assert response.json()[0]["market_cap"] == 2_000_000_000_000
