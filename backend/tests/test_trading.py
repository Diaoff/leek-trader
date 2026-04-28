from datetime import date
from decimal import Decimal


def test_simulate_trade_returns_execution_chain(client, monkeypatch) -> None:
    import app.api.trading as trading_api

    monkeypatch.setattr(trading_api.service, "_get_quote_snapshot", lambda symbol: {"change_percent": 0.0, "is_halted": False})
    monkeypatch.setattr(trading_api.service.risk_service, "_is_trading_time", lambda now=None: True)
    monkeypatch.setattr(trading_api.service, "resolve_simulation_symbol", lambda db: "sh600519")

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


def test_simulate_trade_rejects_when_no_runtime_symbol_available(client, monkeypatch) -> None:
    import app.api.trading as trading_api

    monkeypatch.setattr(trading_api.service, "resolve_simulation_symbol", lambda db: None)

    response = client.post("/api/v1/trading/simulate")

    assert response.status_code == 400
    assert response.json()["detail"] == "no symbol available for simulation"


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
    assert payload["order"]["status"] == "rejected"
    assert payload["order"]["reject_reason"] == "insufficient position"

    orders_response = client.get("/api/v1/orders")
    orders_payload = orders_response.json()
    assert orders_payload[0]["status"] == "rejected"
    assert orders_payload[0]["reject_reason"] == "insufficient position"


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


def test_monitor_position_guards_sells_full_position_on_stop_loss(client, monkeypatch) -> None:
    from app.core.db import SessionLocal
    from app.models.order import Order, OrderSide
    from app.models.position import Position
    from app.trading.service import TradingService
    from sqlalchemy import select

    buy_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 200,
            "price": 100,
        },
    )
    assert buy_response.status_code == 200

    with SessionLocal() as db:
        position = db.scalar(select(Position).where(Position.symbol == "sh600519"))
        assert position is not None
        position.stop_loss_price = 95
        position.take_profit_price = 118
        position.exit_guard_status = "active"
        position.last_buy_date = date(2026, 4, 21)
        db.commit()

        service = TradingService()
        monkeypatch.setattr(service, "_get_quote_snapshot", lambda symbol: {"price": 94.0, "change_percent": -4.0, "is_halted": False})
        result = service.monitor_position_guards(db)

        db.refresh(position)
        sell_orders = db.scalars(select(Order).where(Order.side == OrderSide.SELL).order_by(Order.id.asc())).all()

    assert result["triggered_count"] == 1
    assert result["triggered_orders"][0]["reason"] == "stop_loss"
    assert position.quantity == 0
    assert position.strategy_add_count == 0
    assert position.stop_loss_price is None
    assert position.take_profit_price is None
    assert position.exit_guard_status == "inactive"
    assert len(sell_orders) == 1
    assert sell_orders[0].status == "filled"


def test_monitor_position_guards_skips_when_pending_sell_order_exists(client, monkeypatch) -> None:
    from app.core.db import SessionLocal
    from app.models.order import Order, OrderSide, OrderStatus, OrderType
    from app.models.position import Position
    from app.trading.service import TradingService
    from sqlalchemy import select

    buy_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 200,
            "price": 100,
        },
    )
    assert buy_response.status_code == 200

    with SessionLocal() as db:
        position = db.scalar(select(Position).where(Position.symbol == "sh600519"))
        assert position is not None
        position.stop_loss_price = 95
        position.take_profit_price = 118
        position.exit_guard_status = "active"
        position.last_buy_date = date(2026, 4, 21)
        db.add(
            Order(
                tenant_id=position.tenant_id,
                account_id=position.account_id,
                symbol=position.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                status=OrderStatus.PENDING,
                quantity=100,
                price=Decimal("101.0000"),
                filled_quantity=0,
                filled_price=Decimal("0.0000"),
            )
        )
        db.commit()

        service = TradingService()
        monkeypatch.setattr(service, "_get_quote_snapshot", lambda symbol: {"price": 94.0, "change_percent": -4.0, "is_halted": False})
        result = service.monitor_position_guards(db)

        orders = db.scalars(select(Order).where(Order.symbol == "sh600519").order_by(Order.id.asc())).all()

    assert result["triggered_count"] == 0
    assert result["skipped"] == [{"symbol": "sh600519", "reason": "pending_exit_order"}]
    assert len(orders) == 2
    assert orders[-1].status == "pending"
