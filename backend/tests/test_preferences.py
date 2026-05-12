def test_preferences_defaults_are_created(client) -> None:
    response = client.get("/api/v1/preferences")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == "local"
    assert payload["trading"]["commission_rate"] == 0.0003
    assert payload["trading"]["min_commission"] == 5.0
    assert payload["trading"]["stamp_tax_rate"] == 0.0005
    assert payload["risk_rule_version"]["version"].startswith("risk-rules-v1-")
    assert payload["risk_rule_version"]["threshold_snapshot"] == {
        "max_daily_trades": 20,
        "single_position_limit_pct": 0.2,
        "total_exposure_limit_pct": 0.9,
        "daily_loss_limit_pct": 0.05,
    }
    assert payload["strategy_scheduler"] == {
        "enabled": True,
        "interval_seconds": 300,
        "trading_hours_only": True,
    }
    assert payload["smart_selection"]["enabled"] is True
    assert payload["smart_selection"]["schedule_time"] == "20:00"


def test_preferences_update_round_trips_and_syncs_smart_selection(client) -> None:
    response = client.put(
        "/api/v1/preferences",
        json={
            "trading": {
                "commission_rate": 0.001,
                "min_commission": 2,
                "stamp_tax_rate": 0.002,
                "max_daily_trades": 12,
                "single_position_limit_pct": 0.25,
                "total_exposure_limit_pct": 0.8,
                "daily_loss_limit_pct": 0.03,
            },
            "strategy_scheduler": {
                "enabled": False,
                "interval_seconds": 900,
                "trading_hours_only": False,
            },
            "smart_selection": {
                "enabled": False,
                "config_payload": {
                    "min_score": 40,
                    "max_recommendations": 5,
                    "candidate_pool": {"batch_size": 20},
                    "institution_rating_pool": {"enabled": True, "min_latest_date_rows": 30},
                    "risk_control": {"stop_loss_pct": 4},
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trading"]["commission_rate"] == 0.001
    assert payload["trading"]["min_commission"] == 2.0
    assert payload["trading"]["stamp_tax_rate"] == 0.002
    assert payload["trading"]["max_daily_trades"] == 12
    assert payload["trading"]["single_position_limit_pct"] == 0.25
    assert payload["trading"]["total_exposure_limit_pct"] == 0.8
    assert payload["trading"]["daily_loss_limit_pct"] == 0.03
    assert payload["risk_rule_version"]["threshold_snapshot"]["max_daily_trades"] == 12
    assert payload["risk_rule_version"]["threshold_snapshot"]["daily_loss_limit_pct"] == 0.03
    assert payload["strategy_scheduler"]["enabled"] is False
    assert payload["strategy_scheduler"]["interval_seconds"] == 900
    assert payload["strategy_scheduler"]["trading_hours_only"] is False
    assert payload["smart_selection"]["enabled"] is False
    assert payload["smart_selection"]["config_payload"]["min_score"] == 40
    assert payload["smart_selection"]["config_payload"]["candidate_pool"]["mode"] == "institution_watchlist"
    assert payload["smart_selection"]["config_payload"]["institution_rating_pool"]["min_latest_date_rows"] == 30

    smart_response = client.get("/api/v1/smart-selection/config")
    assert smart_response.status_code == 200
    smart_payload = smart_response.json()
    assert smart_payload["enabled"] is False
    assert smart_payload["config_payload"]["max_recommendations"] == 5
    assert smart_payload["config_payload"]["institution_rating_pool"]["min_latest_date_rows"] == 30
