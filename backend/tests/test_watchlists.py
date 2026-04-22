def test_list_watchlists_returns_empty_by_default(client) -> None:
    response = client.get("/api/v1/watchlists")

    assert response.status_code == 200
    assert response.json() == []


def test_create_watchlist_item_persists(client) -> None:
    create_response = client.post("/api/v1/watchlists", json={"symbol": "sh600519"})

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["symbol"] == "sh600519"
    assert payload["tenant_id"] == "local"
    assert payload["sort_order"] == 0

    list_response = client.get("/api/v1/watchlists")

    assert list_response.status_code == 200
    assert [item["symbol"] for item in list_response.json()] == ["sh600519"]


def test_create_watchlist_item_trims_and_normalizes_symbol(client) -> None:
    response = client.post("/api/v1/watchlists", json={"symbol": " SH600519 "})

    assert response.status_code == 200
    assert response.json()["symbol"] == "sh600519"


def test_duplicate_watchlist_item_is_rejected(client) -> None:
    first_response = client.post("/api/v1/watchlists", json={"symbol": "sh600519"})
    assert first_response.status_code == 200

    duplicate_response = client.post("/api/v1/watchlists", json={"symbol": "sh600519"})

    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["detail"] == "symbol already exists in watchlist"


def test_delete_watchlist_item_removes_it(client) -> None:
    create_response = client.post("/api/v1/watchlists", json={"symbol": "sh600519"})
    item_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/v1/watchlists/{item_id}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted", "id": item_id}
    assert client.get("/api/v1/watchlists").json() == []


def test_delete_missing_watchlist_item_returns_not_found(client) -> None:
    response = client.delete("/api/v1/watchlists/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "watchlist item not found"
