from decimal import Decimal

from app.models.account import Account
from app.models.cash_flow import CashFlow, CashFlowType
from app.models.equity_snapshot import EquitySnapshot
from app.models.order import Order, OrderSide, OrderStatus, OrderType
from app.models.position import Position
from app.models.trade import Trade


def _register_and_login(client, username: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "password",
            "full_name": username,
        },
    )
    assert response.status_code == 200
    login = client.post("/api/v1/auth/login", data={"username": username, "password": "password"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _default_account(db) -> Account:
    account = db.query(Account).first()
    assert account is not None
    return account


def test_reset_trading_state_clears_account_records_and_cash(db, client) -> None:
    account = _default_account(db)
    account.initial_cash = Decimal("1000000.00")
    account.available_cash = Decimal("800000.00")
    account.frozen_cash = Decimal("1000.00")
    account.total_equity = Decimal("900000.00")
    order = Order(
        tenant_id=account.tenant_id,
        account_id=account.id,
        symbol="sh600519",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        status=OrderStatus.FILLED,
        quantity=100,
        price=Decimal("100.00"),
        filled_quantity=100,
        filled_price=Decimal("100.00"),
    )
    db.add(order)
    db.flush()
    db.add_all([
        Trade(
            tenant_id=account.tenant_id,
            account_id=account.id,
            order_id=order.id,
            symbol="sh600519",
            quantity=100,
            price=Decimal("100.00"),
            fee=Decimal("5.00"),
            realized_pnl=Decimal("0.00"),
        ),
        Position(
            tenant_id=account.tenant_id,
            account_id=account.id,
            symbol="sh600519",
            quantity=100,
            available_quantity=100,
            average_cost=Decimal("100.0000"),
            last_price=Decimal("101.0000"),
            unrealized_pnl=Decimal("100.00"),
        ),
        CashFlow(
            tenant_id=account.tenant_id,
            account_id=account.id,
            flow_type=CashFlowType.TRADE,
            amount=Decimal("-10005.00"),
            balance_after=Decimal("800000.00"),
        ),
        EquitySnapshot(
            tenant_id=account.tenant_id,
            account_id=account.id,
            total_equity=Decimal("900000.00"),
            available_cash=Decimal("800000.00"),
            market_value=Decimal("10100.00"),
            unrealized_pnl=Decimal("100.00"),
        ),
    ])
    db.commit()

    response = client.post(
        "/api/v1/devtools/reset-trading-state",
        json={"confirmation": "RESET", "initial_cash": "1200000.00"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_counts"] == {
        "trades": 1,
        "orders": 1,
        "positions": 1,
        "cash_flows": 1,
        "equity_snapshots": 1,
    }
    db.refresh(account)
    assert account.initial_cash == Decimal("1200000.00")
    assert account.available_cash == Decimal("1200000.00")
    assert account.frozen_cash == Decimal("0.00")
    assert account.total_equity == Decimal("1200000.00")
    assert db.query(Trade).count() == 0
    assert db.query(Order).count() == 0
    assert db.query(Position).count() == 0
    assert db.query(CashFlow).count() == 0
    assert db.query(EquitySnapshot).count() == 0


def test_reset_trading_state_requires_confirmation(client) -> None:
    response = client.post("/api/v1/devtools/reset-trading-state", json={"confirmation": "WRONG"})

    assert response.status_code == 422
    assert response.json()["detail"] == "confirmation must be RESET"


def test_reset_trading_state_only_resets_current_user_account(client, db) -> None:
    user_a = _register_and_login(client, "carol")
    user_b = _register_and_login(client, "dave")

    order_a = client.post(
        "/api/v1/orders",
        headers=user_a,
        json={"symbol": "sh600519", "side": "buy", "order_type": "market", "quantity": 100, "price": 100},
    )
    order_b = client.post(
        "/api/v1/orders",
        headers=user_b,
        json={"symbol": "sh600000", "side": "buy", "order_type": "market", "quantity": 100, "price": 10},
    )
    assert order_a.status_code == 200
    assert order_b.status_code == 200

    account_a = db.query(Account).filter(Account.user.has(username="carol")).one()
    account_b = db.query(Account).filter(Account.user.has(username="dave")).one()
    before_a = db.query(Order).filter(Order.account_id == account_a.id).count()
    before_b = db.query(Order).filter(Order.account_id == account_b.id).count()

    response = client.post(
        "/api/v1/devtools/reset-trading-state",
        headers=user_b,
        json={"confirmation": "RESET", "initial_cash": "1500000.00"},
    )

    assert response.status_code == 200
    db.refresh(account_a)
    db.refresh(account_b)
    assert before_a == 1
    assert before_b == 1
    assert account_a.initial_cash != Decimal("1500000.00")
    assert account_b.initial_cash == Decimal("1500000.00")
