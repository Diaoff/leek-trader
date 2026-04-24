def test_list_strategies_returns_seeded_database_strategies(client) -> None:
    response = client.get("/api/v1/strategies")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {"name", "strategy_type", "status", "execution_mode", "parameters", "latest_signal", "signal_symbol", "run_count_today"}.issubset(
        payload[0].keys()
    )
    assert payload[0]["execution_mode"] == "signal_only"
    assert payload[0]["latest_signal"] == "hold"
    assert payload[0]["run_count_today"] == 0


def test_create_update_and_run_strategy_persists_state(client) -> None:
    create_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "测试均线策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 7, "position_pct": 0.2},
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "测试均线策略"
    assert created["status"] == "draft"
    assert created["symbol"] == "sh600036"
    assert created["execution_mode"] == "signal_only"

    update_response = client.patch(
        f"/api/v1/strategies/{created['id']}",
        json={
            "status": "active",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 4, "long_window": 8, "position_pct": 0.15},
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["status"] == "active"
    assert updated["execution_mode"] == "auto_trade"
    assert updated["parameters"] == {"short_window": 4, "long_window": 8, "position_pct": 0.15}

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["strategy_id"] == created["id"]
    assert run_payload["status"] == "success"
    assert run_payload["signal"]["signal"] in {"buy", "sell", "hold"}
    assert run_payload["execution_mode"] == "auto_trade"

    list_response = client.get("/api/v1/strategies")
    refreshed = next(item for item in list_response.json() if item["id"] == created["id"])
    assert refreshed["latest_run_status"] == "success"
    assert refreshed["run_count_today"] == 1
    assert refreshed["total_run_count"] == 1
    assert refreshed["latest_signal"] in {"buy", "sell", "hold"}


def test_signal_only_strategy_does_not_create_order(client) -> None:
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "纯信号策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "signal_only",
            "parameters": {"short_window": 3, "long_window": 7},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution_mode"] == "signal_only"
    assert payload["order_submitted"] is False
    assert payload["reason"] == "signal_only_mode"
    assert client.get("/api/v1/orders").json() == []


def test_auto_trade_strategy_places_order_and_updates_reporting(client) -> None:
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "自动交易策略",
            "symbol": "sh600519",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution_mode"] == "auto_trade"
    assert payload["order_submitted"] is True
    assert payload["order_id"] is not None
    assert payload["order_status"] == "filled"
    assert payload["side"] == "buy"
    assert payload["quantity"] % 100 == 0
    assert payload["quantity"] > 0

    orders = client.get("/api/v1/orders").json()
    summary = client.get("/api/v1/portfolio/summary").json()
    reporting = client.get("/api/v1/reporting/summary").json()

    assert len(orders) == 1
    assert orders[0]["status"] == "filled"
    assert summary["available_cash"] < 1000000.0
    assert reporting["trade_count"] == 1


def test_auto_trade_hold_signal_skips_order(client) -> None:
    created = client.post(
        "/api/v1/strategies",
        json={
            "name": "观望自动策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "execution_mode": "auto_trade",
            "parameters": {"short_window": 3, "long_window": 99, "position_pct": 0.1},
        },
    ).json()

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["signal"]["signal"] == "hold"
    assert payload["order_submitted"] is False
    assert payload["reason"] == "signal_hold"
    assert client.get("/api/v1/orders").json() == []
