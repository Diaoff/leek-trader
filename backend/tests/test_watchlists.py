from sqlalchemy import delete, select


DEFAULT_GROUP_NAMES = ["价投", "观察股", "T0", "清仓", "现"]


def test_default_watchlist_groups_seeded(client) -> None:
    response = client.get("/api/v1/watchlist-groups")

    assert response.status_code == 200
    assert [group["name"] for group in response.json()] == DEFAULT_GROUP_NAMES


def test_initialize_database_reseeds_groups_for_existing_account(db) -> None:
    import app.db.init_db as init_db_module
    from app.models.watchlist_group import WatchlistGroup

    db.execute(delete(WatchlistGroup))
    db.commit()

    init_db_module.initialize_database()
    db.expire_all()

    groups = db.scalars(select(WatchlistGroup).order_by(WatchlistGroup.sort_order.asc(), WatchlistGroup.id.asc())).all()

    assert [group.name for group in groups] == DEFAULT_GROUP_NAMES


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
    assert payload["group_id"] is not None

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


def test_patch_watchlist_item_can_clear_note(client) -> None:
    create_response = client.post("/api/v1/watchlists", json={"symbol": "sh600519", "note": "白酒龙头"})
    item_id = create_response.json()["id"]

    patch_response = client.patch(f"/api/v1/watchlists/{item_id}", json={"note": None})

    assert patch_response.status_code == 200
    assert patch_response.json()["note"] is None


def test_reorder_watchlist_items_keeps_pinned_and_regular_zones(client) -> None:
    first = client.post("/api/v1/watchlists", json={"symbol": "sh600519"}).json()
    second = client.post("/api/v1/watchlists", json={"symbol": "sz300750"}).json()
    third = client.post("/api/v1/watchlists", json={"symbol": "sh600036"}).json()

    client.patch(f"/api/v1/watchlists/{second['id']}", json={"is_pinned": True})

    reorder_response = client.post(
        "/api/v1/watchlists/reorder",
        json={
            "group_id": first["group_id"],
            "pinned_ids": [second["id"]],
            "regular_ids": [third["id"], first["id"]],
        },
    )

    assert reorder_response.status_code == 200

    list_response = client.get("/api/v1/watchlists", params={"group_id": first["group_id"]})

    assert list_response.status_code == 200
    payload = list_response.json()
    assert [item["symbol"] for item in payload] == ["sz300750", "sh600036", "sh600519"]
    assert [item["is_pinned"] for item in payload] == [True, False, False]


def test_watchlist_group_crud_and_reorder(client) -> None:
    create_response = client.post("/api/v1/watchlist-groups", json={"name": "今天买什么"})

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "今天买什么"
    assert created["is_system"] is False

    rename_response = client.patch(f"/api/v1/watchlist-groups/{created['id']}", json={"name": "垃圾股"})

    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "垃圾股"

    list_response = client.get("/api/v1/watchlist-groups")
    group_ids = [group["id"] for group in list_response.json()]
    moved_ids = [group_ids[-1], *group_ids[:-1]]

    reorder_response = client.post("/api/v1/watchlist-groups/reorder", json={"group_ids": moved_ids})

    assert reorder_response.status_code == 200
    assert client.get("/api/v1/watchlist-groups").json()[0]["id"] == created["id"]

    delete_response = client.delete(f"/api/v1/watchlist-groups/{created['id']}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted", "id": created["id"]}
    assert [group["name"] for group in client.get("/api/v1/watchlist-groups").json()] == DEFAULT_GROUP_NAMES


def test_system_watchlist_groups_can_be_deleted(client) -> None:
    groups = client.get("/api/v1/watchlist-groups").json()
    target = next(group for group in groups if group["name"] == "价投")

    response = client.delete(f"/api/v1/watchlist-groups/{target['id']}")

    assert response.status_code == 200
    remaining_names = [group["name"] for group in client.get("/api/v1/watchlist-groups").json()]
    assert "价投" not in remaining_names


def test_all_watchlist_groups_can_be_deleted_without_reseeding(client) -> None:
    groups = client.get("/api/v1/watchlist-groups").json()

    for group in groups:
        response = client.delete(f"/api/v1/watchlist-groups/{group['id']}")
        assert response.status_code == 200

    assert client.get("/api/v1/watchlist-groups").json() == []


def test_deleting_last_group_keeps_watchlist_items_as_ungrouped(client) -> None:
    group_id = client.get("/api/v1/watchlist-groups").json()[0]["id"]
    client.post("/api/v1/watchlists", json={"symbol": "sh600519", "group_id": group_id})

    for group in client.get("/api/v1/watchlist-groups").json():
        delete_response = client.delete(f"/api/v1/watchlist-groups/{group['id']}")
        assert delete_response.status_code == 200

    items = client.get("/api/v1/watchlists").json()

    assert len(items) == 1
    assert items[0]["symbol"] == "sh600519"
    assert items[0]["group_id"] is None


def test_security_search_matches_code_and_pinyin(client) -> None:
    code_response = client.get("/api/v1/securities/search", params={"q": "600519"})

    assert code_response.status_code == 200
    assert code_response.json()
    assert code_response.json()[0]["symbol"] == "sh600519"

    pinyin_response = client.get("/api/v1/securities/search", params={"q": "gzmt"})

    assert pinyin_response.status_code == 200
    assert any(item["symbol"] == "sh600519" for item in pinyin_response.json())
