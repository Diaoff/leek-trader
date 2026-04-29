from datetime import date

from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot


def _bar(symbol: str, trade_date: date, *, trade_status: int | None = 1, is_st: bool | None = False) -> DailyBarSnapshot:
    return DailyBarSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        open_price=10.0,
        close_price=10.5,
        high_price=10.8,
        low_price=9.9,
        volume=1000000.0,
        turnover=12000000.0,
        change_pct=1.5,
        turnover_rate=2.3,
        preclose=10.2,
        trade_status=trade_status,
        pe_ttm=12.1,
        pb_mrq=1.2,
        ps_ttm=2.1,
        pcf_ncf_ttm=3.1,
        is_st=is_st,
    )


def test_daily_bars_source_baostock_reads_database_without_fetch(client, db, monkeypatch) -> None:
    import app.api.market as market_api

    MarketDailyBarStorage(db).upsert_bars([_bar("600000.SH", date(2026, 4, 21))], source="baostock", adjustflag="2")
    monkeypatch.setattr(
        market_api.market_data_service,
        "get_daily_bars_with_source",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not fetch provider when db has baostock bars")),
    )

    response = client.get("/api/v1/market/daily-bars", params={"symbol": "600000.SH", "source": "baostock"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "sh600000"
    assert payload["bars"][0]["trade_date"] == "2026-04-21"
    assert payload["bars"][0]["pe_ttm"] == 12.1


def test_daily_bars_source_baostock_defaults_to_empty_when_missing(client, monkeypatch) -> None:
    import app.api.market as market_api

    monkeypatch.setattr(
        market_api.market_data_service,
        "get_daily_bars_with_source",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("default should not fetch missing baostock data")),
    )

    response = client.get("/api/v1/market/daily-bars", params={"symbol": "600000.SH", "source": "baostock"})

    assert response.status_code == 200
    assert response.json()["bars"] == []


def test_daily_bars_source_baostock_limit_returns_latest_bars_in_ascending_order(client, db) -> None:
    MarketDailyBarStorage(db).upsert_bars(
        [
            _bar("600000.SH", date(2026, 4, 20)),
            _bar("600000.SH", date(2026, 4, 21)),
            _bar("600000.SH", date(2026, 4, 22)),
        ],
        source="baostock",
        adjustflag="2",
    )

    response = client.get("/api/v1/market/daily-bars", params={"symbol": "600000.SH", "source": "baostock", "limit": 2})

    assert response.status_code == 200
    assert [bar["trade_date"] for bar in response.json()["bars"]] == ["2026-04-21", "2026-04-22"]


def test_history_storage_latest_requires_single_symbol_when_limited(db) -> None:
    MarketDailyBarStorage(db).upsert_bars(
        [
            _bar("600000.SH", date(2026, 4, 21)),
            _bar("000001.SZ", date(2026, 4, 22)),
        ],
        source="baostock",
        adjustflag="2",
    )

    try:
        MarketDailyBarStorage(db).list_bars(source="baostock", adjustflag="2", limit=1, latest=True)
    except ValueError as error:
        assert "single symbol" in str(error)
    else:
        raise AssertionError("latest=True should require a single symbol")


def test_baostock_history_sync_api_requires_symbols(client) -> None:
    response = client.post(
        "/api/v1/market/baostock/history/sync",
        json={"symbols": [], "start_date": "2026-04-20", "end_date": "2026-04-21"},
    )

    assert response.status_code == 422


def test_baostock_history_sync_api_rejects_invalid_date_range_before_enqueue(client, monkeypatch) -> None:
    import app.api.market as market_api

    monkeypatch.setattr(
        market_api.sync_baostock_history_task,
        "delay",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("invalid range should not enqueue task")),
    )

    response = client.post(
        "/api/v1/market/baostock/history/sync",
        json={"symbols": ["600000.SH"], "start_date": "2026-04-22", "end_date": "2026-04-21"},
    )

    assert response.status_code == 422


def test_baostock_history_sync_now_reports_incremental_ranges(client, db, monkeypatch) -> None:
    import app.api.market as market_api

    class StubSyncService:
        def __init__(self, db) -> None:
            return None

        def sync_history(self, **kwargs):
            assert kwargs["incremental"] is True
            return type(
                "Result",
                (),
                {
                    "to_dict": lambda self: {
                        "status": "completed",
                        "source": "baostock",
                        "adjustflag": "2",
                        "start_date": "2026-04-01",
                        "end_date": "2026-04-23",
                        "requested_symbols": ["sh600000"],
                        "incremental": True,
                        "resolved_ranges": [
                            {
                                "symbol": "sh600000",
                                "start_date": "2026-04-22",
                                "end_date": "2026-04-23",
                                "skipped": False,
                                "reason": None,
                            }
                        ],
                        "succeeded_symbols": ["sh600000"],
                        "success_count": 1,
                        "failure_count": 0,
                        "failures": [],
                        "bars_upserted": 1,
                    }
                },
            )()

    monkeypatch.setattr(market_api, "BaoStockHistorySyncService", StubSyncService)

    response = client.post(
        "/api/v1/market/baostock/history/sync-now",
        json={
            "symbols": ["600000.SH"],
            "start_date": "2026-04-01",
            "end_date": "2026-04-23",
            "incremental": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["incremental"] is True
    assert payload["resolved_ranges"][0]["start_date"] == "2026-04-22"


def test_rl_dataset_api_returns_stable_sorted_records(client, db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars(
        [
            _bar("sz000001", date(2026, 4, 22), trade_status=1, is_st=False),
            _bar("sh600000", date(2026, 4, 21), trade_status=1, is_st=True),
            _bar("sh600000", date(2026, 4, 20), trade_status=0, is_st=False),
        ],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/market/rl/dataset",
        json={"symbols": ["000001.SZ", "600000.SH"], "start_date": "2026-04-20", "end_date": "2026-04-22"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [record["symbol"] for record in payload["records"]] == ["sh600000", "sz000001"]
    assert payload["records"][0]["is_st"] is True
    assert "pcf_ncf_ttm" in payload["fields"]


def test_rl_dataset_split_api_returns_train_test_partitions(client, db) -> None:
    MarketDailyBarStorage(db).upsert_bars(
        [
            _bar("sh600000", date(2026, 4, 20)),
            _bar("sh600000", date(2026, 4, 21)),
            _bar("sh600000", date(2026, 4, 22)),
        ],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/market/rl/dataset/split",
        json={"symbols": ["600000.SH"], "split_date": "2026-04-22"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "rl-daily-bars/v1"
    assert payload["train"]["count"] == 2
    assert payload["test"]["count"] == 1
    assert payload["feature_groups"]["identity"] == ["symbol", "trade_date"]


def test_rl_dataset_quality_api_reports_data_health(client, db) -> None:
    suspended = _bar("sh600000", date(2026, 4, 20), trade_status=0, is_st=False)
    suspended.pb_mrq = None
    MarketDailyBarStorage(db).upsert_bars(
        [suspended, _bar("sh600000", date(2026, 4, 22), trade_status=1, is_st=True)],
        source="baostock",
        adjustflag="2",
    )

    response = client.post("/api/v1/market/rl/dataset/quality", json={"symbols": ["600000.SH"]})

    assert response.status_code == 200
    report = response.json()["symbol_reports"][0]
    assert report["suspended_rows"] == 1
    assert report["st_rows"] == 1
    assert report["null_counts"]["pb_mrq"] == 1
    assert report["calendar_gap_days"] == ["2026-04-21"]


def test_rl_dataset_features_api_documents_feature_contract(client) -> None:
    response = client.get("/api/v1/market/rl/dataset/features")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "rl-daily-bars/v1"
    assert "pcf_ncf_ttm" in payload["fields"]
    assert payload["feature_groups"]["price"] == ["open_price", "close_price", "high_price", "low_price", "preclose"]


def test_rl_episode_simulate_api_runs_buy_and_hold_baseline(client, db) -> None:
    first = _bar("sh600000", date(2026, 4, 20))
    first.close_price = 10.0
    second = _bar("sh600000", date(2026, 4, 21))
    second.close_price = 12.0
    MarketDailyBarStorage(db).upsert_bars([first, second], source="baostock", adjustflag="2")

    response = client.post(
        "/api/v1/market/rl/episode/simulate",
        json={
            "symbols": ["600000.SH"],
            "policy": "buy_and_hold",
            "initial_cash": 1000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["final_net_worth"] == 1200.0
    assert payload["total_return_pct"] == 20.0
    assert payload["steps"][0]["observation"]["account"]["shares"] == 100


def test_rl_strategy_preview_returns_signal_and_standard_trajectory(client, db) -> None:
    bars = []
    for index in range(30):
        bar = _bar("sh600000", date(2026, 4, 1 + index))
        bar.close_price = 10.0 + index * 0.2
        bar.open_price = bar.close_price * 0.99
        bar.high_price = bar.close_price * 1.01
        bar.low_price = bar.close_price * 0.98
        bars.append(bar)
    MarketDailyBarStorage(db).upsert_bars(bars, source="baostock", adjustflag="2")

    response = client.post(
        "/api/v1/market/rl/strategy-preview",
        json={
            "symbol": "600000.SH",
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
            "parameters": {"rl_policy_mode": "baseline", "max_position_pct": 0.4},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["signal"]["signal"] == "buy"
    assert payload["signal"]["rl_state"]["market_regime"] == "bullish"
    assert payload["trajectory"]["equity_curve"]
    assert payload["trajectory"]["actions"]
    assert payload["trajectory"]["positions"]
    assert payload["trajectory"]["rewards"]
    assert "risk_metrics" in payload["trajectory"]["summary"]


def test_rl_strategy_preview_empty_data_is_explainable(client) -> None:
    response = client.post(
        "/api/v1/market/rl/strategy-preview",
        json={"symbol": "600000.SH", "parameters": {"rl_policy_mode": "baseline"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "empty"
    assert payload["signal"]["signal"] == "hold"
    assert payload["signal"]["trigger_reason"] == "history_unavailable"
    assert payload["trajectory"]["summary"] == {"reason": "no_records"}


def test_rl_dataset_api_includes_stable_manifest_and_keeps_csv_plain(client, db) -> None:
    MarketDailyBarStorage(db).upsert_bars(
        [
            _bar("sh600000", date(2026, 4, 20), trade_status=0, is_st=False),
            _bar("sh600000", date(2026, 4, 21), trade_status=1, is_st=True),
        ],
        source="baostock",
        adjustflag="2",
    )
    request = {"symbols": ["600000.SH"], "start_date": "2026-04-20", "end_date": "2026-04-21"}

    first = client.post("/api/v1/market/rl/dataset", json=request)
    second = client.post("/api/v1/market/rl/dataset", json=request)
    csv_response = client.post("/api/v1/market/rl/dataset.csv", json=request)

    assert first.status_code == 200
    manifest = first.json()["manifest"]
    assert manifest["dataset_id"] == second.json()["manifest"]["dataset_id"]
    assert manifest["filters"] == {"exclude_suspended": True}
    assert manifest["quality_summary"]["total_rows"] == 2
    assert manifest["quality_summary"]["suspended_rows"] == 1
    assert "price" in manifest["normalization_hints"]
    assert "manifest" not in csv_response.text.splitlines()[0]


def test_rl_dataset_split_reports_leakage_checks_and_rejects_invalid_boundary(client, db) -> None:
    MarketDailyBarStorage(db).upsert_bars(
        [
            _bar("sh600000", date(2026, 4, 20)),
            _bar("sh600000", date(2026, 4, 21)),
            _bar("sh600000", date(2026, 4, 22)),
        ],
        source="baostock",
        adjustflag="2",
    )

    response = client.post(
        "/api/v1/market/rl/dataset/split",
        json={"symbols": ["600000.SH"], "start_date": "2026-04-20", "end_date": "2026-04-22", "split_date": "2026-04-22"},
    )
    invalid = client.post(
        "/api/v1/market/rl/dataset/split",
        json={"symbols": ["600000.SH"], "start_date": "2026-04-20", "end_date": "2026-04-22", "split_date": "2026-04-20"},
    )

    assert response.status_code == 200
    checks = response.json()["leakage_checks"]
    assert checks["status"] == "passed"
    assert checks["train_end_date"] == "2026-04-21"
    assert checks["test_start_date"] == "2026-04-22"
    assert response.json()["manifest"]["options"]["split_date"] == "2026-04-22"
    assert invalid.status_code == 422


def test_rl_batch_evaluation_run_now_isolates_symbol_failures_and_ranks(client, db) -> None:
    first = _bar("sh600000", date(2026, 4, 20))
    first.close_price = 10.0
    second = _bar("sh600000", date(2026, 4, 21))
    second.close_price = 12.0
    third = _bar("sz000001", date(2026, 4, 20))
    third.close_price = 10.0
    fourth = _bar("sz000001", date(2026, 4, 21))
    fourth.close_price = 11.0
    MarketDailyBarStorage(db).upsert_bars([first, second, third, fourth], source="baostock", adjustflag="2")

    response = client.post(
        "/api/v1/market/rl/batch-evaluation/run-now",
        json={
            "symbols": ["000001.SZ", "600000.SH", "000002.SZ"],
            "policy": "buy_and_hold",
            "initial_cash": 1000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success_count"] == 2
    assert payload["failure_count"] == 1
    assert payload["failures"] == [{"symbol": "sz000002", "reason": "no_records"}]
    assert [item["symbol"] for item in payload["ranking"]] == ["sh600000", "sz000001"]


def test_rl_episode_simulate_api_replays_rl_stock_actions(client, db) -> None:
    first = _bar("sh600000", date(2026, 4, 20))
    first.close_price = 10.0
    second = _bar("sh600000", date(2026, 4, 21))
    second.close_price = 12.0
    third = _bar("sh600000", date(2026, 4, 22))
    third.close_price = 11.0
    MarketDailyBarStorage(db).upsert_bars([first, second, third], source="baostock", adjustflag="2")

    response = client.post(
        "/api/v1/market/rl/episode/simulate",
        json={
            "symbols": ["600000.SH"],
            "policy": "cash",
            "action_sequence": [[1, 1.0], [3, 0.0], [2, 1.0]],
            "action_encoding": "rl_stock_one_based",
            "initial_cash": 1000.0,
            "commission_rate": 0.0,
            "slippage_rate": 0.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["policy"] == "action_replay"
    assert [action["action_type"] for action in payload["actions"]] == ["buy", "hold", "sell"]
    assert payload["summary"]["risk_metrics"]["turnover_pct"] == 210.0
