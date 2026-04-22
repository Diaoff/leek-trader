from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_list_strategies_returns_strategy_payload() -> None:
    response = client.get("/api/v1/strategies")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {"name", "strategy_type", "status", "parameters", "latest_signal", "signal_symbol"}.issubset(payload[0].keys())
    assert payload[0]["latest_signal"] in {"buy", "sell", "hold"}
