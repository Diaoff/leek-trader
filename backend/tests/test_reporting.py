from datetime import datetime, timedelta
from decimal import Decimal


ADVANCED_REPORTING_KEYS = [
    "annualized_return_pct",
    "annualized_volatility_pct",
    "sharpe_ratio",
    "calmar_ratio",
]


def test_reporting_summary_returns_zeroed_metrics_before_trades(client) -> None:
    response = client.get("/api/v1/reporting/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trade_count"] == 0
    assert payload["realized_pnl"] == 0.0
    assert payload["win_rate"] == 0.0
    assert payload["cumulative_return"] == 0.0
    assert payload["profit_factor"] == 0.0
    assert payload["max_drawdown"] == 0.0
    assert payload["avg_win"] == 0.0
    assert payload["avg_loss"] == 0.0
    for key in ADVANCED_REPORTING_KEYS:
        assert payload[key] is None


def test_reporting_summary_returns_nullable_advanced_metrics_for_single_snapshot(client) -> None:
    from app.core.db import SessionLocal
    from app.models.account import Account
    from app.models.equity_snapshot import EquitySnapshot
    from sqlalchemy import select

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.name == "模拟账户"))
        assert account is not None
        db.query(EquitySnapshot).where(EquitySnapshot.account_id == account.id).delete()
        db.add(
            EquitySnapshot(
                tenant_id=account.tenant_id,
                account_id=account.id,
                total_equity=Decimal("1000000.00"),
                available_cash=Decimal("1000000.00"),
                market_value=Decimal("0.00"),
                unrealized_pnl=Decimal("0.00"),
                recorded_at=datetime(2026, 1, 1),
            )
        )
        db.commit()

    payload = client.get("/api/v1/reporting/summary").json()

    for key in ADVANCED_REPORTING_KEYS:
        assert payload[key] is None


def test_reporting_summary_calculates_advanced_metrics_from_snapshots(client) -> None:
    from app.core.db import SessionLocal
    from app.models.account import Account
    from app.models.equity_snapshot import EquitySnapshot
    from sqlalchemy import select

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.name == "模拟账户"))
        assert account is not None
        db.query(EquitySnapshot).where(EquitySnapshot.account_id == account.id).delete()
        base_date = datetime(2026, 1, 1)
        for offset, equity in enumerate(["1000000.00", "1030000.00", "1010000.00", "1060000.00"]):
            db.add(
                EquitySnapshot(
                    tenant_id=account.tenant_id,
                    account_id=account.id,
                    total_equity=Decimal(equity),
                    available_cash=Decimal(equity),
                    market_value=Decimal("0.00"),
                    unrealized_pnl=Decimal("0.00"),
                    recorded_at=base_date + timedelta(days=offset),
                )
            )
        db.commit()

    payload = client.get("/api/v1/reporting/summary").json()

    assert payload["annualized_return_pct"] is not None
    assert payload["annualized_return_pct"] > 0
    assert payload["annualized_volatility_pct"] is not None
    assert payload["annualized_volatility_pct"] > 0
    assert payload["sharpe_ratio"] is not None
    assert payload["calmar_ratio"] is not None
    assert payload["max_drawdown"] > 0


def test_reporting_summary_returns_null_calmar_without_drawdown(client) -> None:
    from app.core.db import SessionLocal
    from app.models.account import Account
    from app.models.equity_snapshot import EquitySnapshot
    from sqlalchemy import select

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.name == "模拟账户"))
        assert account is not None
        db.query(EquitySnapshot).where(EquitySnapshot.account_id == account.id).delete()
        for offset, equity in enumerate(["1000000.00", "1010000.00", "1020000.00"]):
            db.add(
                EquitySnapshot(
                    tenant_id=account.tenant_id,
                    account_id=account.id,
                    total_equity=Decimal(equity),
                    available_cash=Decimal(equity),
                    market_value=Decimal("0.00"),
                    unrealized_pnl=Decimal("0.00"),
                    recorded_at=datetime(2026, 1, 1) + timedelta(days=offset),
                )
            )
        db.commit()

    payload = client.get("/api/v1/reporting/summary").json()

    assert payload["annualized_return_pct"] is not None
    assert payload["calmar_ratio"] is None


def test_reporting_summary_and_curve_update_after_trades(client) -> None:
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
    from datetime import date

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

    summary_response = client.get("/api/v1/reporting/summary")
    curve_response = client.get("/api/v1/reporting/equity-curve")
    monthly_response = client.get("/api/v1/reporting/monthly-stats")
    yearly_response = client.get("/api/v1/reporting/yearly-stats")

    assert summary_response.status_code == 200
    assert curve_response.status_code == 200
    assert monthly_response.status_code == 200
    assert yearly_response.status_code == 200

    summary = summary_response.json()
    curve = curve_response.json()
    monthly = monthly_response.json()
    yearly = yearly_response.json()

    assert summary["trade_count"] == 2
    assert summary["realized_pnl"] == 984.5
    assert summary["win_rate"] == 0.5
    assert summary["cumulative_return"] == 0.0009845
    assert summary["profit_factor"] == 0.0
    assert summary["max_drawdown"] >= 0.0
    assert summary["avg_win"] == 984.5
    assert summary["avg_loss"] == 0.0
    assert set(ADVANCED_REPORTING_KEYS).issubset(summary.keys())
    assert len(curve) >= 2
    assert curve[-1]["total_equity"] == 1000984.5
    assert len(monthly) >= 1
    assert monthly[-1]["trade_count"] == 2
    assert monthly[-1]["realized_pnl"] == 984.5
    assert len(yearly) >= 1
    assert yearly[-1]["trade_count"] == 2
    assert yearly[-1]["ending_equity"] == 1000984.5


def test_equity_curve_grows_after_summary_refresh(client) -> None:
    initial_curve = client.get("/api/v1/reporting/equity-curve").json()
    client.get("/api/v1/portfolio/summary")
    updated_curve = client.get("/api/v1/reporting/equity-curve").json()

    assert len(updated_curve) >= len(initial_curve)
