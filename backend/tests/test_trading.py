from datetime import date


def test_simulate_trade_returns_execution_chain(client, monkeypatch) -> None:
    import app.api.trading as trading_api

    monkeypatch.setattr(trading_api.service, "_get_quote_snapshot", lambda symbol: {"change_percent": 0.0, "is_halted": False})
    monkeypatch.setattr(trading_api.service.risk_service, "_is_trading_time", lambda now=None: True)

    response = client.post("/api/v1/trading/simulate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert len(payload["risk_checks"]) >= 6
    assert payload["execution"]["matched"] is True
    assert payload["order"]["status"] == "filled"
    assert payload["account"]["available_cash"] < 1000000.0

    accounts_response = client.get("/api/v1/accounts")
    orders_response = client.get("/api/v1/orders")

    assert accounts_response.status_code == 200
    assert orders_response.status_code == 200
    accounts_payload = accounts_response.json()
    orders_payload = orders_response.json()

    assert len(accounts_payload) == 1
    assert accounts_payload[0]["available_cash"] == "990000.00"
    assert len(orders_payload) == 1
    assert orders_payload[0]["symbol"] == "sh600519"
    assert orders_payload[0]["status"] == "filled"


def test_create_sell_order_reduces_position_and_records_realized_pnl(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"change_percent": 0.0, "is_halted": False})
    monkeypatch.setattr(orders_api.service.risk_service, "_is_trading_time", lambda now=None: True)

    buy_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )
    assert buy_response.status_code == 200

    from app.core.db import SessionLocal
    from app.models.position import Position
    from sqlalchemy import select

    with SessionLocal() as db:
        position = db.scalar(select(Position).where(Position.symbol == "sh600519"))
        assert position is not None
        position.last_buy_date = date(2026, 4, 21)
        db.commit()

    sell_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "sell",
            "order_type": "market",
            "quantity": 100,
            "price": 110,
        },
    )

    assert sell_response.status_code == 200
    payload = sell_response.json()
    assert payload["status"] == "accepted"
    assert payload["trade"]["realized_pnl"] == 1000.0
    assert payload["position"]["quantity"] == 0
    assert payload["cash_flow"]["amount"] == 11000.0
    assert payload["account"]["available_cash"] == 1001000.0


def test_create_sell_order_rejects_when_position_insufficient(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"change_percent": 0.0, "is_halted": False})
    monkeypatch.setattr(orders_api.service.risk_service, "_is_trading_time", lambda now=None: True)

    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "sell",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["rejection_reason"] == "insufficient position"


def test_create_order_rejects_outside_trading_hours(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"change_percent": 0.0, "is_halted": False})
    monkeypatch.setattr(orders_api.service.risk_service, "_is_trading_time", lambda now=None: False)

    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["rejection_reason"] == "outside trading hours"


def test_create_order_rejects_halted_symbol(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"change_percent": 0.0, "is_halted": True})
    monkeypatch.setattr(orders_api.service.risk_service, "_is_trading_time", lambda now=None: True)

    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["rejection_reason"] == "symbol halted"


def test_create_buy_order_rejects_limit_up_symbol(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"change_percent": 10.0, "is_halted": False})
    monkeypatch.setattr(orders_api.service.risk_service, "_is_trading_time", lambda now=None: True)

    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["rejection_reason"] == "symbol at limit up"


def test_create_sell_order_rejects_t_plus_one(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"change_percent": 0.0, "is_halted": False})
    monkeypatch.setattr(orders_api.service.risk_service, "_is_trading_time", lambda now=None: True)

    buy_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )
    assert buy_response.status_code == 200

    sell_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "sell",
            "order_type": "market",
            "quantity": 100,
            "price": 110,
        },
    )

    assert sell_response.status_code == 200
    payload = sell_response.json()
    assert payload["status"] == "rejected"
    assert payload["rejection_reason"] == "t+1 sell restriction"
