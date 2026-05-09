from app.schemas.quote import QuoteRead


def test_quote_stream_sends_subscription_and_quotes(client, monkeypatch) -> None:
    import app.api.quote_stream as stream_module

    class FakeQuoteService:
        def list_quotes(self, symbols: list[str]) -> list[QuoteRead]:
            return [
                QuoteRead(
                    symbol=symbols[0],
                    price=100.0,
                    change_percent=1.23,
                    volume=1000.0,
                    timestamp="2026-05-09T09:30:00+08:00",
                    is_halted=False,
                )
            ]

    monkeypatch.setattr(stream_module, "service", FakeQuoteService())

    with client.websocket_connect("/api/v1/quotes/stream?symbols=sh600519&interval_seconds=1") as websocket:
        subscribed = websocket.receive_json()
        payload = websocket.receive_json()

    assert subscribed == {"type": "subscribed", "symbols": ["sh600519"], "interval_seconds": 1.0}
    assert payload["type"] == "quotes"
    assert payload["quotes"][0]["symbol"] == "sh600519"
    assert payload["quotes"][0]["price"] == 100.0
