from __future__ import annotations

from datetime import date

from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot


def _daily_bar(
    symbol: str,
    trade_date: date,
    close_price: float,
    *,
    trade_status: int | None = 1,
    is_st: bool | None = False,
    pe_ttm: float | None = 12.3,
) -> DailyBarSnapshot:
    return DailyBarSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        open_price=close_price - 0.2,
        close_price=close_price,
        high_price=close_price + 0.3,
        low_price=close_price - 0.4,
        volume=1_000_000.0,
        turnover=close_price * 1_000_000.0,
        trade_status=trade_status,
        is_st=is_st,
        pe_ttm=pe_ttm,
    )


def _patch_strategy_signal(monkeypatch, payload: dict[str, object]) -> None:
    import app.api.strategies as strategies_api

    monkeypatch.setattr(
        strategies_api.service,
        "_evaluate_strategy",
        lambda strategy, symbol: {**payload, "symbol": symbol},
    )
    monkeypatch.setattr(strategies_api.service, "_is_opening_trade_window", lambda now=None: True)
    monkeypatch.setattr(
        strategies_api.service.trading_service,
        "_get_quote_snapshot",
        lambda symbol: {"price": 100.0, "change_percent": 0.0, "is_halted": False},
    )


def test_market_daily_bars_and_quality_report_are_explainable(client, db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars(
        [
            _daily_bar("sh600000", date(2026, 4, 20), 10.5, trade_status=0, pe_ttm=None),
            _daily_bar("sh600000", date(2026, 4, 22), 10.8, is_st=True),
        ],
        source="baostock",
        adjustflag="2",
    )

    bars_response = client.get(
        "/api/v1/market/daily-bars",
        params={"symbol": "600000.SH", "source": "baostock", "limit": 10},
    )
    quality_response = client.post(
        "/api/v1/market/quality/daily-bars",
        json={"symbols": ["600000.SH"], "source": "baostock", "adjustflag": "2"},
    )

    assert bars_response.status_code == 200
    bars_payload = bars_response.json()
    assert bars_payload["symbol"] == "sh600000"
    assert bars_payload["source"].startswith("BaoStock")
    assert {item["trade_date"] for item in bars_payload["bars"]} == {"2026-04-20", "2026-04-22"}

    assert quality_response.status_code == 200
    quality_payload = quality_response.json()
    assert quality_payload["status"] == "ready"
    assert quality_payload["total_rows"] == 2
    assert quality_payload["nullable_fields"]
    symbol_report = quality_payload["symbol_reports"][0]
    assert symbol_report["symbol"] == "sh600000"
    assert symbol_report["suspended_rows"] == 1
    assert symbol_report["st_rows"] == 1
    assert symbol_report["null_counts"]["pe_ttm"] == 1
    assert symbol_report["calendar_gap_days"] == ["2026-04-21"]


def test_strategy_run_produces_traceable_signal_without_order(client, monkeypatch) -> None:
    _patch_strategy_signal(
        monkeypatch,
        {
            "signal": "buy",
            "strength": "strong",
            "trigger_reason": "golden_cross",
            "entry_price_ref": 100.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 115.0,
            "position_pct": 0.1,
            "market_regime": "bullish",
            "requires_recommendation_confirmation": False,
            "filter_passed": True,
            "filter_reasons": [],
            "trend_ok": True,
            "volume_ok": True,
            "volatility_ok": True,
            "stretch_ok": True,
            "market_regime_bias": "supportive",
        },
    )

    create_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "核心链路信号策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 5, "position_pct": 0.1},
        },
    )
    assert create_response.status_code == 200
    strategy_id = create_response.json()["id"]

    run_response = client.post(f"/api/v1/strategies/{strategy_id}/run")
    latest_response = client.get("/api/v1/strategies/runs/latest", params={"strategy_id": strategy_id})

    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["status"] == "success"
    assert run_payload["signal"]["signal"] == "buy"
    assert run_payload["execution_mode"] == "signal_only"
    assert run_payload["order_submitted"] is False
    assert run_payload["reason"] == "signal_only_mode"
    assert run_payload["execution_blockers"] == ["signal_only_mode"]
    assert run_payload["items"][0]["trigger_reason"] == "golden_cross"
    assert latest_response.status_code == 200
    assert latest_response.json()["id"] == run_payload["id"]
    assert client.get("/api/v1/orders").json() == []


def test_risk_to_trading_records_acceptance_rejection_and_cash(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(
        orders_api.service,
        "_get_quote_snapshot",
        lambda symbol: {"price": 100.0, "change_percent": 0.0, "is_halted": False},
    )
    monkeypatch.setattr(orders_api.service.risk_service, "_is_trading_time", lambda now=None: True)

    accepted_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )
    rejected_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100_000,
            "price": 100,
        },
    )
    accounts_response = client.get("/api/v1/accounts")
    orders_response = client.get("/api/v1/orders")

    assert accepted_response.status_code == 200
    accepted = accepted_response.json()
    assert accepted["status"] == "accepted"
    assert accepted["execution"]["matched"] is True
    assert accepted["execution"]["mode"] == "paper"
    assert accepted["execution"]["symbol"] == "sh600519"
    assert accepted["order"]["status"] == "filled"
    assert accepted["risk_rule_version"].startswith("risk-rules-v1-")
    assert accepted["trade"]["fee"] == 5.0
    assert accepted["cash_flow"]["amount"] == -10005.0
    assert accepted["account"]["available_cash"] == 989995.0
    assert all(item["passed"] for item in accepted["risk_checks"])

    assert rejected_response.status_code == 200
    rejected = rejected_response.json()
    assert rejected["status"] == "rejected"
    assert rejected["risk_rule_version"] == accepted["risk_rule_version"]
    assert rejected["rejection_reason"] in {"insufficient cash", "single position limit exceeded"}
    assert rejected["order"]["status"] == "rejected"
    assert any(not item["passed"] and item["reason"] == rejected["rejection_reason"] for item in rejected["risk_checks"])

    assert accounts_response.status_code == 200
    assert accounts_response.json()[0]["available_cash"] == "989995.00"
    assert orders_response.status_code == 200
    listed_orders = orders_response.json()
    assert [item["status"] for item in listed_orders] == ["rejected", "filled"]
    assert [item["risk_rule_version"] for item in listed_orders] == [accepted["risk_rule_version"], accepted["risk_rule_version"]]


def test_positions_portfolio_and_reporting_stay_consistent_after_trade(client, monkeypatch) -> None:
    import app.api.positions as positions_api
    import app.api.portfolio as portfolio_api

    class QuoteSnapshot:
        def __init__(self, symbol: str, price: float) -> None:
            self.symbol = symbol
            self.price = price

    monkeypatch.setattr(
        positions_api.service.quote_service,
        "list_quotes",
        lambda symbols: [QuoteSnapshot(symbol, 120.0) for symbol in symbols],
    )
    monkeypatch.setattr(
        portfolio_api.service.quote_service,
        "list_quotes",
        lambda symbols: [QuoteSnapshot(symbol, 120.0) for symbol in symbols],
    )

    order_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )
    assert order_response.status_code == 200

    positions_response = client.get("/api/v1/positions")
    portfolio_response = client.get("/api/v1/portfolio/summary")
    reporting_summary_response = client.get("/api/v1/reporting/summary")
    equity_curve_response = client.get("/api/v1/reporting/equity-curve")

    assert positions_response.status_code == 200
    positions = positions_response.json()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "sh600519"
    assert positions[0]["quantity"] == 100
    assert positions[0]["last_price"] == "120.0000"
    assert positions[0]["unrealized_pnl"] == "1995.00"

    assert portfolio_response.status_code == 200
    portfolio = portfolio_response.json()
    assert portfolio["available_cash"] == 989995.0
    assert portfolio["market_value"] == 12000.0
    assert portfolio["unrealized_pnl"] == 1995.0
    assert portfolio["total_equity"] == 1001995.0

    assert reporting_summary_response.status_code == 200
    reporting = reporting_summary_response.json()
    assert reporting["trade_count"] == 1
    assert reporting["realized_pnl"] == 0.0
    assert reporting["cumulative_return"] == 0.001995

    assert equity_curve_response.status_code == 200
    curve = equity_curve_response.json()
    assert curve[-1]["total_equity"] == 1001995.0


def test_market_source_health_explains_primary_and_fallback(client, db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars(
        [
            _daily_bar("sh600000", date(2026, 4, 20), 10.5),
            _daily_bar("sh600000", date(2026, 4, 21), 10.8),
            _daily_bar("sz000001", date(2026, 4, 21), 12.8),
        ],
        source="baostock",
        adjustflag="2",
    )
    storage.upsert_bars(
        [_daily_bar("sh600000", date(2026, 4, 21), 10.7)],
        source="tencent",
        adjustflag="2",
    )

    response = client.get(
        "/api/v1/market/health/sources",
        params=[
            ("symbols", "600000.SH"),
            ("symbols", "000001.SZ"),
            ("end_date", "2026-04-21"),
            ("sources", "baostock"),
            ("sources", "tencent"),
            ("sources", "sina"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["primary_source"] == "baostock"
    assert payload["fallback_sources"] == ["tencent"]
    assert payload["failover_policy"]["network_probe"] is False

    sources = {item["source"]: item for item in payload["sources"]}
    assert sources["baostock"]["role"] == "primary"
    assert sources["baostock"]["status"] == "healthy"
    assert sources["baostock"]["symbol_count"] == 2
    assert sources["tencent"]["role"] == "fallback"
    assert sources["tencent"]["status"] == "partial"
    assert sources["tencent"]["missing_symbols"] == ["sz000001"]
    assert sources["sina"]["role"] == "unavailable"
    assert sources["sina"]["status"] == "empty"
