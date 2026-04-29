from decimal import Decimal

from app.models.account import Account
from app.models.cash_flow import CashFlow, CashFlowType
from app.models.equity_snapshot import EquitySnapshot
from app.models.order import Order, OrderSide, OrderStatus, OrderType
from app.models.position import Position
from app.models.trade import Trade


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
