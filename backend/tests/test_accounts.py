def test_list_accounts_returns_bootstrapped_account(client) -> None:
    response = client.get("/api/v1/accounts")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "模拟账户"
    assert payload[0]["available_cash"] == "1000000.00"
