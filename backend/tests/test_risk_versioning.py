from app.risk.versioning import RiskRuleVersionService
from app.schemas.preferences import TradingPreferences


def test_risk_rule_version_is_deterministic_for_same_thresholds() -> None:
    service = RiskRuleVersionService()
    preferences = TradingPreferences(max_daily_trades=12, single_position_limit_pct=0.25)

    first = service.current_version(preferences, changed_at="2026-05-11T00:00:00+00:00")
    second = service.current_version(preferences, changed_at="2026-05-12T00:00:00+00:00")

    assert first.version == second.version
    assert first.threshold_snapshot == second.threshold_snapshot
    assert first.threshold_snapshot["max_daily_trades"] == 12
    assert first.threshold_snapshot["single_position_limit_pct"] == 0.25


def test_risk_rule_version_changes_when_threshold_changes() -> None:
    service = RiskRuleVersionService()

    original = service.current_version(TradingPreferences(max_daily_trades=12))
    changed = service.current_version(TradingPreferences(max_daily_trades=13))

    assert original.version != changed.version


def test_risk_rule_version_endpoint_returns_snapshot(client) -> None:
    update_response = client.put(
        "/api/v1/preferences",
        json={"trading": {"max_daily_trades": 12, "total_exposure_limit_pct": 0.8}},
    )
    response = client.get("/api/v1/preferences/risk-rule-version")

    assert update_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == update_response.json()["risk_rule_version"]["version"]
    assert payload["threshold_snapshot"]["max_daily_trades"] == 12
    assert payload["threshold_snapshot"]["total_exposure_limit_pct"] == 0.8
    assert payload["change_source"] == "trading_preferences"
    assert payload["description"]
    assert "订单风控结果" in "\n".join(payload["notes"])


def test_non_risk_preference_update_does_not_change_risk_rule_changed_at(client) -> None:
    first_response = client.get("/api/v1/preferences/risk-rule-version")
    update_response = client.put(
        "/api/v1/preferences",
        json={"strategy_scheduler": {"interval_seconds": 600}},
    )
    second_response = client.get("/api/v1/preferences/risk-rule-version")

    assert first_response.status_code == 200
    assert update_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["version"] == first_response.json()["version"]
    assert second_response.json()["changed_at"] == first_response.json()["changed_at"]
