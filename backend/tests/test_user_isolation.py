from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, username: str) -> dict[str, str]:
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


def test_personal_endpoints_require_auth(client: TestClient) -> None:
    auth_header = client.headers.pop("Authorization")
    try:
        assert client.get("/api/v1/watchlists").status_code == 401
        assert client.get("/api/v1/accounts").status_code == 401
        assert client.get("/api/v1/preferences").status_code == 401
        assert client.get("/api/v1/ai/config").status_code == 401
        assert client.get("/api/v1/strategies").status_code == 401
    finally:
        client.headers.update({"Authorization": auth_header})


def test_sensitive_backend_endpoints_require_auth(client: TestClient) -> None:
    auth_header = client.headers.pop("Authorization")
    sync_payload = {"symbols": ["600000.SH"], "start_date": "2026-04-20", "end_date": "2026-04-21"}
    batch_payload = {"symbols": ["600000.SH"], "policy": "cash"}

    try:
        assert client.get("/api/v1/monitoring/metrics").status_code == 401
        assert client.get("/api/v1/monitoring/system/stats").status_code == 401
        assert client.get("/api/v1/monitoring/logs/latest").status_code == 401
        assert client.get("/api/v1/monitoring/async-tasks/summary").status_code == 401
        assert client.post("/api/v1/monitoring/async-tasks/match-pending-orders").status_code == 401
        assert client.post("/api/v1/market/baostock/history/sync", json=sync_payload).status_code == 401
        assert client.post("/api/v1/market/baostock/history/sync-now", json=sync_payload).status_code == 401
        assert client.post("/api/v1/market/rl/batch-evaluation", json=batch_payload).status_code == 401
        assert client.post("/api/v1/market/rl/batch-evaluation/run-now", json=batch_payload).status_code == 401
    finally:
        client.headers.update({"Authorization": auth_header})


def test_sensitive_backend_endpoints_reject_non_admin_user(client: TestClient) -> None:
    user_headers = _register_and_login(client, "nonadmin")
    sync_payload = {"symbols": ["600000.SH"], "start_date": "2026-04-20", "end_date": "2026-04-21"}
    batch_payload = {"symbols": ["600000.SH"], "policy": "cash"}

    assert client.get("/api/v1/monitoring/metrics", headers=user_headers).status_code == 403
    assert client.get("/api/v1/monitoring/system/stats", headers=user_headers).status_code == 403
    assert client.get("/api/v1/monitoring/logs/latest", headers=user_headers).status_code == 403
    assert client.get("/api/v1/monitoring/async-tasks/summary", headers=user_headers).status_code == 403
    assert client.post("/api/v1/monitoring/async-tasks/match-pending-orders", headers=user_headers).status_code == 403
    assert client.post("/api/v1/market/baostock/history/sync", json=sync_payload, headers=user_headers).status_code == 403
    assert client.post("/api/v1/market/baostock/history/sync-now", json=sync_payload, headers=user_headers).status_code == 403
    assert client.post("/api/v1/market/rl/batch-evaluation", json=batch_payload, headers=user_headers).status_code == 403
    assert client.post("/api/v1/market/rl/batch-evaluation/run-now", json=batch_payload, headers=user_headers).status_code == 403


def test_public_read_only_endpoints_remain_available_without_auth(client: TestClient) -> None:
    auth_header = client.headers.pop("Authorization")
    try:
        assert client.get("/").status_code == 200
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/monitoring/health").status_code == 200
        assert client.get("/api/v1/market/overview").status_code == 200
        assert client.get("/api/v1/market/daily-bars", params={"symbol": "600000.SH"}).status_code == 200
        assert client.get("/api/v1/securities/search", params={"q": "600"}).status_code == 200
    finally:
        client.headers.update({"Authorization": auth_header})


def test_users_have_isolated_watchlists_preferences_ai_and_accounts(client: TestClient) -> None:
    user_a = _register_and_login(client, "alice")
    user_b = _register_and_login(client, "bob")

    created = client.post("/api/v1/watchlists", json={"symbol": "sh600519"}, headers=user_a)
    assert created.status_code == 200
    assert client.get("/api/v1/watchlists", headers=user_a).json()[0]["symbol"] == "sh600519"
    assert client.get("/api/v1/watchlists", headers=user_b).json() == []

    preference_update = client.put(
        "/api/v1/preferences",
        headers=user_a,
        json={"trading": {"commission_rate": 0.001}},
    )
    assert preference_update.status_code == 200
    assert client.get("/api/v1/preferences", headers=user_a).json()["trading"]["commission_rate"] == 0.001
    assert client.get("/api/v1/preferences", headers=user_b).json()["trading"]["commission_rate"] == 0.0003

    ai_update = client.put(
        "/api/v1/ai/config",
        headers=user_a,
        json={"base_url": "https://llm.example.com", "api_key": "secret-a", "model": "model-a"},
    )
    assert ai_update.status_code == 200
    assert client.get("/api/v1/ai/config", headers=user_a).json()["model"] == "model-a"
    assert client.get("/api/v1/ai/config", headers=user_b).json()["configured"] is False

    accounts_a = client.get("/api/v1/accounts", headers=user_a).json()
    accounts_b = client.get("/api/v1/accounts", headers=user_b).json()
    assert len(accounts_a) == 1
    assert len(accounts_b) == 1
    assert accounts_a[0]["id"] != accounts_b[0]["id"]


def test_orders_and_reset_are_isolated_by_user(client: TestClient) -> None:
    user_a = _register_and_login(client, "carol")
    user_b = _register_and_login(client, "dave")

    order = client.post(
        "/api/v1/orders",
        headers=user_a,
        json={"symbol": "sh600519", "side": "buy", "order_type": "market", "quantity": 100, "price": 100},
    )
    assert order.status_code == 200
    assert len(client.get("/api/v1/orders", headers=user_a).json()) == 1
    assert client.get("/api/v1/orders", headers=user_b).json() == []
    assert client.get("/api/v1/positions", headers=user_a).json()[0]["symbol"] == "sh600519"
    assert client.get("/api/v1/positions", headers=user_b).json() == []

    reset = client.post("/api/v1/devtools/reset-trading-state", headers=user_b, json={"confirmation": "RESET"})
    assert reset.status_code == 200
    assert len(client.get("/api/v1/orders", headers=user_a).json()) == 1
    assert client.get("/api/v1/orders", headers=user_b).json() == []
