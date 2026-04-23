def test_list_strategies_returns_seeded_database_strategies(client) -> None:
    response = client.get("/api/v1/strategies")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {"name", "strategy_type", "status", "parameters", "latest_signal", "signal_symbol", "run_count_today"}.issubset(
        payload[0].keys()
    )
    assert payload[0]["latest_signal"] == "hold"
    assert payload[0]["run_count_today"] == 0


def test_create_update_and_run_strategy_persists_state(client) -> None:
    create_response = client.post(
        "/api/v1/strategies",
        json={
            "name": "测试均线策略",
            "symbol": "sh600036",
            "strategy_type": "moving_average",
            "parameters": {"short_window": 3, "long_window": 7},
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "测试均线策略"
    assert created["status"] == "draft"
    assert created["symbol"] == "sh600036"

    update_response = client.patch(
        f"/api/v1/strategies/{created['id']}",
        json={
            "status": "active",
            "parameters": {"short_window": 4, "long_window": 8},
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["status"] == "active"
    assert updated["parameters"] == {"short_window": 4, "long_window": 8}

    run_response = client.post(f"/api/v1/strategies/{created['id']}/run")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["strategy_id"] == created["id"]
    assert run_payload["status"] == "success"
    assert run_payload["signal"]["signal"] in {"buy", "sell", "hold"}

    list_response = client.get("/api/v1/strategies")
    refreshed = next(item for item in list_response.json() if item["id"] == created["id"])
    assert refreshed["latest_run_status"] == "success"
    assert refreshed["run_count_today"] == 1
    assert refreshed["total_run_count"] == 1
    assert refreshed["latest_signal"] in {"buy", "sell", "hold"}
