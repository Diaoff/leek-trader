import pytest

from app.models.order import Order, OrderStatus


def test_create_market_order_persists_and_lists_order(client) -> None:
    create_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["status"] == "accepted"
    assert payload["risk_rule_version"].startswith("risk-rules-v1-")
    assert payload["order"]["status"] == "filled"
    assert any(item["name"] == "warn_near_single_position_limit" for item in payload["risk_checks"])

    list_response = client.get("/api/v1/orders")

    assert list_response.status_code == 200
    orders = list_response.json()
    assert len(orders) == 1
    assert orders[0]["symbol"] == "sh600519"
    assert orders[0]["side"] == "buy"
    assert orders[0]["status"] == "filled"
    assert orders[0]["risk_rule_version"] == payload["risk_rule_version"]

    events_response = client.get("/api/v1/reporting/events", params={"order_id": payload["order"]["id"]})
    assert events_response.status_code == 200
    event_payload = events_response.json()
    event_types = [item["event_type"] for item in event_payload]
    assert "risk_decision" in event_types
    assert "order_event" in event_types
    assert "trade_execution" in event_types
    assert "position_change" in event_types
    assert "equity_snapshot" in event_types
    risk_decision = next(item for item in event_payload if item["event_type"] == "risk_decision")
    assert risk_decision["risk_rule_version"] == payload["risk_rule_version"]
    assert risk_decision["payload"]["decision"] in {"pass", "warn"}
    assert isinstance(risk_decision["payload"]["checks"], list)
    assert "rejection_reason" in risk_decision["payload"]
    assert any(
        item["payload"].get("degraded_reason") == "manual_order_without_strategy_run"
        for item in event_payload
    )


def test_create_limit_order_stays_pending_and_can_be_cancelled(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"price": 101.0, "change_percent": 0.0, "is_halted": False})

    create_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "limit",
            "quantity": 100,
            "price": 100,
        },
    )

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["status"] == "accepted"
    assert payload["risk_rule_version"].startswith("risk-rules-v1-")
    assert payload["order"]["status"] == "pending"
    order_id = payload["order"]["id"]

    list_response = client.get("/api/v1/orders")
    assert list_response.status_code == 200
    listed_order = next(item for item in list_response.json() if item["id"] == order_id)
    assert listed_order["risk_rule_version"] == payload["risk_rule_version"]

    cancel_response = client.post(f"/api/v1/orders/{order_id}/cancel")

    assert cancel_response.status_code == 200
    cancel_payload = cancel_response.json()
    assert cancel_payload["status"] == "accepted"
    assert cancel_payload["order"]["status"] == "cancelled"


def test_cannot_cancel_filled_order(client) -> None:
    create_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
            "price": 100,
        },
    )
    assert create_response.status_code == 200
    order_id = create_response.json()["order"]["id"]

    cancel_response = client.post(f"/api/v1/orders/{order_id}/cancel")

    assert cancel_response.status_code == 200
    payload = cancel_response.json()
    assert payload["status"] == "rejected"
    assert payload["message"] == "only pending orders can be cancelled"


def test_match_pending_buy_limit_order(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"price": 99.0, "change_percent": 0.0, "is_halted": False})

    create_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "limit",
            "quantity": 100,
            "price": 100,
        },
    )
    assert create_response.status_code == 200

    match_response = client.post("/api/v1/orders/match-pending")
    assert match_response.status_code == 200
    payload = match_response.json()
    assert payload["matched_count"] == 1
    assert payload["matched_orders"][0]["status"] == "filled"


def test_unmatched_limit_order_stays_pending(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"price": 101.0, "change_percent": 0.0, "is_halted": False})

    create_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "limit",
            "quantity": 100,
            "price": 100,
        },
    )
    assert create_response.status_code == 200
    order_id = create_response.json()["order"]["id"]

    match_response = client.post("/api/v1/orders/match-pending")
    assert match_response.status_code == 200
    assert match_response.json()["matched_count"] == 0

    orders = client.get("/api/v1/orders").json()
    matched = next(item for item in orders if item["id"] == order_id)
    assert matched["status"] == "pending"
    assert matched["risk_rule_version"] == create_response.json()["risk_rule_version"]


def test_pending_limit_order_auto_matches_on_orders_read(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"price": 99.0, "change_percent": 0.0, "is_halted": False})

    create_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "limit",
            "quantity": 100,
            "price": 100,
        },
    )
    assert create_response.status_code == 200
    order_id = create_response.json()["order"]["id"]

    orders = client.get("/api/v1/orders").json()
    matched = next(item for item in orders if item["id"] == order_id)
    assert matched["status"] == "filled"
    assert matched["risk_rule_version"].startswith("risk-rules-v1-")


def test_risk_checks_include_configured_thresholds_and_actual_values(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(
        orders_api.service,
        "_get_quote_snapshot",
        lambda symbol: {"price": 100.0, "change_percent": 0.0, "is_halted": False},
    )
    monkeypatch.setattr(orders_api.service.risk_service, "_is_trading_time", lambda now=None: True)

    preference_response = client.put(
        "/api/v1/preferences",
        json={
            "trading": {
                "single_position_limit_pct": 0.01,
                "total_exposure_limit_pct": 0.5,
                "max_daily_trades": 30,
            }
        },
    )
    assert preference_response.status_code == 200

    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "market",
            "quantity": 200,
            "price": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["rejection_reason"] == "single position limit exceeded"

    checks = {item["name"]: item for item in payload["risk_checks"]}
    assert checks["check_daily_trade_limit"]["threshold"] == 30
    assert checks["check_daily_trade_limit"]["actual"] == 0
    assert checks["check_trading_time"]["threshold"] is True
    assert checks["check_trading_time"]["actual"] is True
    assert checks["check_symbol_status"]["threshold"] is False
    assert checks["check_symbol_status"]["actual"] is False
    assert checks["check_position_limit"]["passed"] is False
    assert checks["check_position_limit"]["threshold"] == 10000.0
    assert checks["check_position_limit"]["actual"] == 20006.0
    assert checks["check_position_limit"]["limit_pct"] == 0.01
    assert checks["check_total_exposure_limit"]["threshold"] == 500000.0
    assert checks["check_total_exposure_limit"]["actual"] == 20006.0
    assert checks["check_total_exposure_limit"]["limit_pct"] == 0.5
    assert checks["warn_near_single_position_limit"]["severity"] == "warn"
    assert checks["warn_near_single_position_limit"]["suggested_action"] == "review_position_size"

    order_id = payload["order"]["id"]
    events_payload = client.get("/api/v1/reporting/events", params={"order_id": order_id}).json()
    risk_decision = next(item for item in events_payload if item["event_type"] == "risk_decision")
    rejected_event = next(
        item
        for item in events_payload
        if item["event_type"] == "order_event" and item["payload"].get("event_type") == "rejected"
    )
    assert risk_decision["risk_rule_version"] == payload["risk_rule_version"]
    assert risk_decision["payload"]["decision"] == "reject"
    assert risk_decision["payload"]["rejection_reason"] == payload["rejection_reason"]
    assert risk_decision["payload"]["checks"]
    assert rejected_event["payload"]["reason"] == payload["rejection_reason"]
    assert rejected_event["payload"]["to_status"] == "rejected"


def test_order_events_are_sorted_and_include_status_transitions(client, monkeypatch) -> None:
    import app.api.orders as orders_api

    monkeypatch.setattr(orders_api.service, "_get_quote_snapshot", lambda symbol: {"price": 101.0, "change_percent": 0.0, "is_halted": False})
    create_response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "sh600519",
            "side": "buy",
            "order_type": "limit",
            "quantity": 100,
            "price": 100,
        },
    )
    order_id = create_response.json()["order"]["id"]
    cancel_response = client.post(f"/api/v1/orders/{order_id}/cancel")
    assert cancel_response.status_code == 200

    events_response = client.get("/api/v1/reporting/events", params={"order_id": order_id})
    assert events_response.status_code == 200
    payload = events_response.json()
    assert payload == sorted(payload, key=lambda item: (item["occurred_at"], item["id"]))
    order_events = [item for item in payload if item["event_type"] == "order_event"]
    assert order_events[0]["payload"]["event_type"] == "created"
    assert order_events[-1]["payload"]["event_type"] == "cancelled"


def test_order_status_machine_rejects_illegal_terminal_transition() -> None:
    order = Order(status=OrderStatus.PENDING)

    assert order.transition_to(OrderStatus.ACCEPTED) == OrderStatus.PENDING
    assert order.status == OrderStatus.ACCEPTED
    assert order.transition_to(OrderStatus.EXPIRED) == OrderStatus.ACCEPTED
    assert order.status == OrderStatus.EXPIRED

    with pytest.raises(ValueError, match="illegal order status transition"):
        order.transition_to(OrderStatus.PENDING)
