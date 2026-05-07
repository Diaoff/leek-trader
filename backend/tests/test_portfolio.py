from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.market.providers.base import QuoteSnapshot
from app.portfolio.service import PortfolioService


class StubQuoteService:
    def __init__(self, price: float) -> None:
        self.price = price

    def list_quotes(self, symbols: list[str]):
        return [
            QuoteSnapshot(
                symbol=symbols[0],
                price=self.price,
                change_percent=1.0,
                volume=1000.0,
                timestamp=datetime(2026, 4, 22, 9, 30, 0, tzinfo=ZoneInfo("UTC")),
                is_halted=False,
            )
        ]


def test_portfolio_summary_returns_initialized_account_metrics(client) -> None:
    response = client.get("/api/v1/portfolio/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_equity"] == 1000000.0
    assert payload["available_cash"] == 1000000.0
    assert payload["frozen_cash"] == 0.0
    assert payload["market_value"] == 0.0
    assert payload["unrealized_pnl"] == 0.0


def test_portfolio_summary_counts_frozen_cash_in_total_assets(db) -> None:
    from decimal import Decimal

    from app.core.config import settings
    from app.models.account import Account
    from sqlalchemy import select

    account = db.scalar(select(Account).where(Account.tenant_id == settings.default_tenant_id))
    assert account is not None
    account.available_cash = Decimal("990000.00")
    account.frozen_cash = Decimal("10000.00")
    account.total_equity = Decimal("990000.00")
    db.commit()

    payload = PortfolioService().get_summary(db)

    assert payload["available_cash"] == 990000.0
    assert payload["frozen_cash"] == 10000.0
    assert payload["market_value"] == 0.0
    assert payload["total_equity"] == 1000000.0


def test_portfolio_summary_changes_after_order(client, monkeypatch) -> None:
    import app.api.portfolio as portfolio_api

    monkeypatch.setattr(portfolio_api.service, "quote_service", StubQuoteService(100.0))

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

    response = client.get("/api/v1/portfolio/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_equity"] == 999995.0
    assert payload["available_cash"] == 989995.0
    assert payload["frozen_cash"] == 0.0
    assert payload["market_value"] == 10000.0
    assert payload["unrealized_pnl"] == -5.0


def test_portfolio_summary_updates_after_sell_order(client, monkeypatch) -> None:
    import app.api.portfolio as portfolio_api
    from app.core.db import SessionLocal
    from app.models.position import Position
    from sqlalchemy import select

    monkeypatch.setattr(portfolio_api.service, "quote_service", StubQuoteService(110.0))

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

    with SessionLocal() as db:
        position = db.scalar(select(Position).where(Position.symbol == "sh600519"))
        assert position is not None
        position.last_buy_date = date(2026, 4, 21)
        db.commit()

    client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "sell",
            "order_type": "market",
            "quantity": 100,
            "price": 110,
        },
    )

    response = client.get("/api/v1/portfolio/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available_cash"] == 1000984.5
    assert payload["frozen_cash"] == 0.0
    assert payload["market_value"] == 0.0


def test_portfolio_service_refreshes_unrealized_pnl_from_quotes(client) -> None:
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

    with SessionLocal() as db:
        payload = PortfolioService(quote_service=StubQuoteService(120.0)).get_summary(db)

    assert payload["market_value"] == 12000.0
    assert payload["unrealized_pnl"] == 1995.0
    assert payload["total_equity"] == 1001995.0
    assert payload["frozen_cash"] == 0.0


def test_pending_limit_order_auto_matches_on_portfolio_read(client, monkeypatch) -> None:
    import app.api.portfolio as portfolio_api

    monkeypatch.setattr(portfolio_api.trading_service, "_get_quote_snapshot", lambda symbol: {"price": 99.0, "change_percent": 0.0, "is_halted": False})
    monkeypatch.setattr(portfolio_api.service, "quote_service", StubQuoteService(99.0))

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

    response = client.get("/api/v1/portfolio/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["frozen_cash"] == 0.0
    assert payload["market_value"] == 9900.0
