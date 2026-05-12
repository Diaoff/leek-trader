from datetime import date, timedelta

from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot


def _bar(symbol: str, trade_date: date, close_price: float) -> DailyBarSnapshot:
    return DailyBarSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        open_price=close_price * 0.99,
        close_price=close_price,
        high_price=close_price * 1.01,
        low_price=close_price * 0.98,
        volume=1000000.0,
        turnover=12000000.0,
    )


def _seed_bars(db, symbol: str, base_price: float = 10.0) -> None:
    start = date(2026, 1, 1)
    MarketDailyBarStorage(db).upsert_bars(
        [_bar(symbol, start + timedelta(days=index), base_price + index * 0.2) for index in range(80)],
        source="baostock",
        adjustflag="2",
    )


def test_portfolio_backtest_combines_equity_and_contributions(client, db) -> None:
    _seed_bars(db, "sh600519", 10.0)
    _seed_bars(db, "sz000001", 8.0)

    response = client.post(
        "/api/v1/backtest/portfolio/run",
        json={
            "symbols": ["sh600519", "sz000001"],
            "strategy_type": "moving_average",
            "initial_cash": 100000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "max_position_pct": 0.6,
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.2},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["symbols"] == ["sh600519", "sz000001"]
    assert payload["weights"] == [0.5, 0.5]
    assert payload["equity_curve"]
    assert payload["summary"]["result_type"] == "portfolio_backtest"
    assert len(payload["summary"]["contributions"]) == 2
    assert payload["summary"]["diagnostics"]["has_data_gap"] is False
    assert payload["final_net_worth"] > 0


def test_portfolio_backtest_normalizes_explicit_weights(client, db) -> None:
    _seed_bars(db, "sh600519", 10.0)
    _seed_bars(db, "sz000001", 8.0)

    response = client.post(
        "/api/v1/backtest/portfolio/run",
        json={
            "symbols": ["sh600519", "sz000001"],
            "weights": [2, 1],
            "strategy_type": "moving_average",
            "initial_cash": 90000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.2},
        },
    )

    assert response.status_code == 200
    weights = response.json()["weights"]
    assert round(sum(weights), 6) == 1.0
    assert weights[0] == round(2 / 3, 8)
    assert weights[1] == round(1 / 3, 8)


def test_portfolio_backtest_rejects_invalid_weights(client) -> None:
    response = client.post(
        "/api/v1/backtest/portfolio/run",
        json={
            "symbols": ["sh600519", "sz000001"],
            "weights": [1, 0],
            "strategy_type": "moving_average",
        },
    )

    assert response.status_code == 422
