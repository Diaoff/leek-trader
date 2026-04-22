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
    assert payload["order"]["status"] == "filled"

    list_response = client.get("/api/v1/orders")

    assert list_response.status_code == 200
    orders = list_response.json()
    assert len(orders) == 1
    assert orders[0]["symbol"] == "sh600519"
    assert orders[0]["side"] == "buy"
    assert orders[0]["status"] == "filled"


def test_create_limit_order_stays_pending_and_can_be_cancelled(client) -> None:
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
    assert payload["order"]["status"] == "pending"
    order_id = payload["order"]["id"]

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
