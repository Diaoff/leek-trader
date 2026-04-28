from datetime import datetime
from zoneinfo import ZoneInfo

from app.market.providers.base import QuoteSnapshot
from app.portfolio.service import PortfolioService


class StubQuoteService:
    def list_quotes(self, symbols: list[str]):
        return [
            QuoteSnapshot(
                symbol=symbols[0],
                price=120.0,
                change_percent=1.0,
                volume=1000.0,
                timestamp=datetime(2026, 4, 22, 9, 30, 0, tzinfo=ZoneInfo("UTC")),
                is_halted=False,
            )
        ]


def test_list_positions_returns_empty_list_before_trade(client) -> None:
    response = client.get("/api/v1/positions")

    assert response.status_code == 200
    assert response.json() == []


def test_list_positions_returns_open_position_after_buy(client) -> None:
    create_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )
    assert create_response.status_code == 200

    response = client.get("/api/v1/positions")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["symbol"] == "sh600519"
    assert payload[0]["quantity"] == 100
    assert payload[0]["available_quantity"] == 100
    assert payload[0]["stop_loss_price"] is None
    assert payload[0]["take_profit_price"] is None
    assert payload[0]["strategy_add_count"] == 0
    assert payload[0]["exit_guard_status"] == "inactive"
    assert payload[0]["exit_trigger_reason"] is None
    assert payload[0]["exit_triggered_at"] is None


def test_portfolio_service_refreshes_position_prices_from_quotes(client) -> None:
    client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )

    from app.core.db import SessionLocal
    from app.models.position import Position
    from sqlalchemy import select

    with SessionLocal() as db:
        service = PortfolioService(quote_service=StubQuoteService())
        service.refresh_positions_with_quotes(db, 1)
        position = db.scalar(select(Position).where(Position.symbol == "sh600519"))

    assert position is not None
    assert str(position.last_price) == "120.0000"
    assert str(position.unrealized_pnl) == "2000.00"


def test_pending_limit_order_auto_matches_on_positions_read(client, monkeypatch) -> None:
    import app.api.positions as positions_api

    monkeypatch.setattr(positions_api.trading_service, "_get_quote_snapshot", lambda symbol: {"price": 99.0, "change_percent": 0.0, "is_halted": False})

    create_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "limit",
            "quantity": 100,
            "price": 100,
        },
    )
    assert create_response.status_code == 200

    response = client.get("/api/v1/positions")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["symbol"] == "sh600519"
