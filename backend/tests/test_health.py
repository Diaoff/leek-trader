def test_health_check_returns_expected_payload(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["services"]["api"] == "up"
    assert payload["tenant"] == "local"
