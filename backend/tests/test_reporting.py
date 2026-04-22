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
    assert summary["realized_pnl"] == 1000.0
    assert summary["win_rate"] == 0.5
    assert summary["cumulative_return"] == 0.001
    assert summary["profit_factor"] == 0.0
    assert summary["max_drawdown"] >= 0.0
    assert summary["avg_win"] == 1000.0
    assert summary["avg_loss"] == 0.0
    assert len(curve) >= 2
    assert curve[-1]["total_equity"] == 1001000.0
    assert len(monthly) >= 1
    assert monthly[-1]["trade_count"] == 2
    assert monthly[-1]["realized_pnl"] == 1000.0
    assert len(yearly) >= 1
    assert yearly[-1]["trade_count"] == 2
    assert yearly[-1]["ending_equity"] == 1001000.0


def test_equity_curve_grows_after_summary_refresh(client) -> None:
    initial_curve = client.get("/api/v1/reporting/equity-curve").json()
    client.get("/api/v1/portfolio/summary")
    updated_curve = client.get("/api/v1/reporting/equity-curve").json()

    assert len(updated_curve) >= len(initial_curve)
