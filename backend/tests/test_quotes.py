from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_list_quotes_returns_quote_payload() -> None:
    response = client.get("/api/v1/quotes")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    assert {"symbol", "price", "change_percent", "volume", "timestamp", "is_halted"}.issubset(payload[0].keys())
