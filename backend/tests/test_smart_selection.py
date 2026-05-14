from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.celery_app import celery_app
from app.db import init_db as init_db_module
from app.models.smart_selection_config import SmartSelectionConfig
from app.models.watchlist import WatchlistItem
from app.market.providers.base import DailyBarSnapshot
from app.market.providers.base import ResearchStatusSnapshot, StockFundFlowSnapshot
from app.schemas.smart_selection import SmartSelectionConfigUpdate
from app.models.smart_selection_institution_pool_item import SmartSelectionInstitutionPoolItem
from app.smart_selection.service import SmartSelectionService
from app.smart_selection.service import (
    ADataDragonTigerSource,
    AkshareDragonTigerSource,
    DragonTigerAnalyzer,
    DragonTigerSourceResult,
    FundFlowSourceResult,
)


def _test_config_payload() -> dict:
    return {
        "min_score": 20,
        "max_recommendations": 5,
        "price_range": [3, 500],
        "candidate_pool": {
            "dynamic_enabled": True,
            "batch_size": 50,
            "watchlist_codes": ["111111"],
            "fallback_codes": ["222222"],
        },
        "institution_rating_pool": {
            "enabled": False,
        },
        "risk_control": {
            "stop_loss_pct": 5,
            "target_gain_pct": 15,
            "min_risk_reward": 1.0,
            "max_position_pct": 18,
            "weak_market_position_pct": 25,
            "neutral_market_position_pct": 45,
            "strong_market_position_pct": 65,
        },
        "scoring": {
            "market_bonus": 6,
            "market_penalty": 8,
            "heat_bonus": 6,
            "liquidity_bonus": 8,
            "volatility_penalty": 10,
            "lhb_red_bonus": 10,
            "lhb_black_penalty": 100,
        },
        "lhb_keywords": {"black": ["拉萨"], "white": ["江苏路"]},
    }


def _add_watchlist_item(
    db,
    symbol: str,
    *,
    sort_order: int = 0,
    is_pinned: bool = False,
) -> WatchlistItem:
    item = WatchlistItem(
        tenant_id="local",
        symbol=symbol,
        group_id=None,
        sort_order=sort_order,
        is_pinned=is_pinned,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _daily_bars_from_closes(closes: list[float]) -> list[DailyBarSnapshot]:
    return [
        DailyBarSnapshot(
            symbol="sh600519",
            trade_date=date(2026, 1, 1) + timedelta(days=index),
            open_price=close,
            close_price=close,
            high_price=close + 1,
            low_price=close - 1,
            volume=1_000_000 + index * 10_000,
        )
        for index, close in enumerate(closes)
    ]


def test_get_kline_bars_uses_unified_history_service(monkeypatch) -> None:
    bars = _daily_bars_from_closes([10.0] * 30)

    class StubHistoryService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def get_daily_bars(self, symbol: str, limit: int = 60):
            self.calls.append((symbol, limit))
            return bars

    history_service = StubHistoryService()
    service = SmartSelectionService(history_service=history_service)
    monkeypatch.setattr(
        service,
        "_fetch_sina_kline_bars",
        lambda symbol, days: (_ for _ in ()).throw(AssertionError("legacy sina path should not be used")),
    )

    result = service._get_kline_bars("301667.SZ", days=320)

    assert result == bars
    assert history_service.calls == [("301667.SZ", 320)]


def test_nine_turn_detects_completed_buy_setup() -> None:
    closes = [100, 101, 102, 103, 99, 98, 97, 96, 95, 94, 93, 92, 91]

    result = SmartSelectionService._nine_turn(closes)

    assert result.direction == "buy"
    assert result.count == 9
    assert result.completed is True
    assert SmartSelectionService._nine_turn_buy_score(result.count) == 15.0


def test_nine_turn_detects_completed_sell_setup() -> None:
    closes = [91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103]

    result = SmartSelectionService._nine_turn(closes)

    assert result.direction == "sell"
    assert result.count == 9
    assert result.completed is True


def test_nine_turn_scores_partial_buy_setup_in_tech_analysis() -> None:
    closes = [100.0] * 34 + [99.0, 98.0, 97.0, 96.0, 95.0, 94.0]

    result = SmartSelectionService()._analyze_tech(
        _daily_bars_from_closes(closes),
        market_state={"regime": "neutral"},
        config=_test_config_payload(),
    )

    assert result["valid"] is True
    assert result["dim"]["nine_turn"] > 0
    assert result["nine_turn_direction"] == "buy"
    assert result["nine_turn_count"] == 6
    assert result["nine_turn_completed"] is False
    assert "神奇九转买入序列 6/9" in result["signals"]


def test_nine_turn_sell_setup_is_risk_signal_not_positive_score() -> None:
    closes = [90.0] * 31 + [91.0, 92.0, 93.0, 94.0, 95.0, 96.0, 97.0, 98.0, 99.0]

    result = SmartSelectionService()._analyze_tech(
        _daily_bars_from_closes(closes),
        market_state={"regime": "neutral"},
        config=_test_config_payload(),
    )

    assert result["dim"]["nine_turn"] == 0
    assert result["nine_turn_direction"] == "sell"
    assert result["nine_turn_count"] == 9
    assert result["nine_turn_completed"] is True
    assert "神奇九转卖出序列 9/9" in result["signals"]
    assert "神奇九转卖出信号" in result["signals"]


def test_nine_turn_keeps_zero_when_no_setup_exists() -> None:
    result = SmartSelectionService._nine_turn([100, 101, 99, 102, 100, 101, 99, 102, 100, 101])

    assert result.direction == "none"
    assert result.count == 0
    assert result.completed is False


def test_fund_flow_score_scales_with_inflow_strength() -> None:
    closes = [100.0 + index * 0.1 for index in range(40)]

    result = SmartSelectionService()._analyze_tech(
        _daily_bars_from_closes(closes),
        market_state={"regime": "neutral"},
        config=_test_config_payload(),
    )

    assert result["valid"] is True
    assert 0 < result["dim"]["fund_flow"] < 25
    assert result["fund_flow_ratio_10"] > 0
    assert result["fund_flow_ratio_20"] > 0


def test_fund_flow_score_reaches_cap_only_for_strong_inflow() -> None:
    closes = [100.0 * (1.05 ** index) for index in range(40)]

    result = SmartSelectionService()._analyze_tech(
        _daily_bars_from_closes(closes),
        market_state={"regime": "neutral"},
        config=_test_config_payload(),
    )

    assert result["valid"] is True
    assert result["dim"]["fund_flow"] == 25


def test_fund_flow_score_is_zero_for_outflow() -> None:
    closes = [140.0 - index * 0.5 for index in range(40)]

    result = SmartSelectionService()._analyze_tech(
        _daily_bars_from_closes(closes),
        market_state={"regime": "neutral"},
        config=_test_config_payload(),
    )

    assert result["valid"] is True
    assert result["dim"]["fund_flow"] == 0
    assert result["fund_flow_ratio_10"] < 0
    assert result["fund_flow_ratio_20"] < 0


def test_adata_fund_flow_signal_scores_from_snapshot() -> None:
    service = SmartSelectionService()

    signal = service._build_fund_flow_signal(
        StockFundFlowSnapshot(
            symbol="sh600519",
            trade_date="2026-05-12",
            main_net_inflow=2.1e8,
            super_large_net_inflow=1.2e8,
            large_net_inflow=5.5e7,
            main_net_ratio=12.6,
            source="adata",
            status=ResearchStatusSnapshot(code="ok"),
        )
    )

    assert signal["status"]["code"] == "ok"
    assert signal["source"] == "adata"
    assert signal["score"] == 25.0
    assert signal["raw"]["main_net_inflow"] == 2.1e8
    assert signal["score_detail"]["breakdown"]["main_net_inflow"] == 14.0


def test_adata_fund_flow_signal_degrades_to_neutral() -> None:
    class StubFundFlowSource:
        name = "adata"

        def fetch(self, symbol: str) -> FundFlowSourceResult:
            return FundFlowSourceResult(
                success=False,
                symbol=symbol,
                source_name="adata",
                status="empty_response",
                notes="upstream unavailable",
            )

    service = SmartSelectionService(fund_flow_sources=[StubFundFlowSource()])

    signal = service._resolve_fund_flow_signal("sh600519")

    assert signal["score"] == 0.0
    assert signal["status"]["code"] == "empty_response"
    assert signal["status"]["degraded"] is True
    assert "中性处理" in signal["signals"][0]


def test_dragon_tiger_analyzer_prefers_adata_source() -> None:
    class StubADataSource:
        name = "adata"

        def fetch(self, lookback_days: int) -> DragonTigerSourceResult:
            return DragonTigerSourceResult(
                success=True,
                trade_date="2026-05-12",
                source_name="adata",
                rows=[{"营业部": "江苏路证券营业部", "股票": "贵州茅台", "净额": "2.4亿"}],
                status="ok",
            )

    class StubAkshareSource:
        name = "akshare"

        def fetch(self, lookback_days: int) -> DragonTigerSourceResult:
            raise AssertionError("fallback source should not be used")

    analyzer = DragonTigerAnalyzer(_test_config_payload(), sources=[StubADataSource(), StubAkshareSource()])

    assert analyzer.fetch() is True
    signal = analyzer.classify("贵州茅台")
    assert analyzer.source_name == "adata"
    assert analyzer.fallback_used is False
    assert signal.tag == "RED"
    assert signal.detail["source"] == "adata"


def test_dragon_tiger_analyzer_falls_back_to_akshare() -> None:
    class StubADataSource:
        name = "adata"

        def fetch(self, lookback_days: int) -> DragonTigerSourceResult:
            return DragonTigerSourceResult(success=False, source_name="adata", status="schema_change", notes="missing field")

    class StubAkshareSource:
        name = "akshare"

        def fetch(self, lookback_days: int) -> DragonTigerSourceResult:
            return DragonTigerSourceResult(
                success=True,
                trade_date="2026-05-12",
                source_name="akshare",
                rows=[{"营业部": "江苏路证券营业部", "股票": "贵州茅台", "净额": "9000万"}],
                status="ok",
            )

    analyzer = DragonTigerAnalyzer(_test_config_payload(), sources=[StubADataSource(), StubAkshareSource()])

    assert analyzer.fetch() is True
    signal = analyzer.classify("贵州茅台")
    assert analyzer.source_name == "akshare"
    assert analyzer.fallback_used is True
    assert signal.detail["fallback_used"] is True


def test_dragon_tiger_analyzer_disables_when_all_sources_fail() -> None:
    class StubADataSource:
        name = "adata"

        def fetch(self, lookback_days: int) -> DragonTigerSourceResult:
            return DragonTigerSourceResult(success=False, source_name="adata", status="dependency_error", notes="adata missing")

    class StubAkshareSource:
        name = "akshare"

        def fetch(self, lookback_days: int) -> DragonTigerSourceResult:
            return DragonTigerSourceResult(success=False, source_name="akshare", status="empty_response")

    analyzer = DragonTigerAnalyzer(_test_config_payload(), sources=[StubADataSource(), StubAkshareSource()])

    assert analyzer.fetch() is False
    assert analyzer.enabled is False
    assert analyzer.status in {"empty_response", "dependency_error"}


def test_smart_selection_config_can_be_loaded_and_updated(client) -> None:
    response = client.get("/api/v1/smart-selection/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == "local"
    assert payload["enabled"] is True
    assert payload["schedule_time"] == "20:00"
    assert payload["config_payload"]["candidate_pool"]["watchlist_source"] == "user_watchlist"
    assert "watchlist_codes" not in payload["config_payload"]["candidate_pool"]
    assert "fallback_codes" not in payload["config_payload"]["candidate_pool"]

    update_response = client.put(
        "/api/v1/smart-selection/config",
        json={"enabled": False, "config_payload": _test_config_payload()},
    )

    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["enabled"] is False
    assert update_payload["config_payload"]["candidate_pool"]["mode"] == "institution_watchlist"
    assert update_payload["config_payload"]["candidate_pool"]["watchlist_source"] == "user_watchlist"
    assert "watchlist_codes" not in update_payload["config_payload"]["candidate_pool"]
    assert "fallback_codes" not in update_payload["config_payload"]["candidate_pool"]


def test_initialize_database_prunes_duplicate_legacy_smart_selection_configs(db) -> None:
    duplicate = SmartSelectionConfig(
        tenant_id="local",
        user_id=None,
        enabled=False,
        schedule_time="08:30",
        config_payload={"min_score": 99},
    )
    db.add(duplicate)
    db.commit()

    init_db_module.initialize_database()

    rows = db.query(SmartSelectionConfig).order_by(SmartSelectionConfig.id).all()

    assert len(rows) == 1
    assert rows[0].user_id == 1
    assert rows[0].tenant_id == "local"


def test_initialize_database_handles_duplicate_legacy_singletons(db) -> None:
    duplicate = SmartSelectionConfig(
        tenant_id="local",
        user_id=None,
        enabled=False,
        schedule_time="08:30",
        config_payload={"min_score": 88},
    )
    db.add(duplicate)
    db.commit()

    init_db_module.initialize_database()

    rows = db.query(SmartSelectionConfig).order_by(SmartSelectionConfig.id).all()

    assert len(rows) == 1
    assert rows[0].user_id == 1


def test_trigger_smart_selection_run_enqueues_task(client, monkeypatch) -> None:
    import app.api.smart_selection as smart_selection_api

    calls: dict[str, object] = {}

    class DummyResult:
        id = "task-smart-selection-1"

    def fake_apply_async(*, kwargs=None):
        calls["kwargs"] = kwargs
        return DummyResult()

    monkeypatch.setattr(smart_selection_api.run_smart_selection_task, "apply_async", fake_apply_async)

    response = client.post("/api/v1/smart-selection/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["task_id"] == "task-smart-selection-1"
    assert calls["kwargs"]["triggered_by"] == "manual"
    assert calls["kwargs"]["tenant_id"] == "local"


def test_triggered_smart_selection_latest_exposes_progress(client, monkeypatch) -> None:
    import app.api.smart_selection as smart_selection_api

    class DummyResult:
        id = "task-smart-selection-progress"

    monkeypatch.setattr(smart_selection_api.run_smart_selection_task, "apply_async", lambda kwargs=None: DummyResult())

    run_response = client.post("/api/v1/smart-selection/run")
    latest_response = client.get("/api/v1/smart-selection/latest")

    assert run_response.status_code == 200
    assert latest_response.status_code == 200
    latest_task = latest_response.json()["latest_task"]
    assert latest_task["status"] == "queued"
    assert latest_task["progress_step"] == 0
    assert latest_task["progress_total"] == 6
    assert latest_task["progress_label"] == "准备运行"
    assert latest_task["fund_flow_stats"] == {"available": False}


def test_smart_selection_run_api_exposes_fund_flow_stats(client, db) -> None:
    service = SmartSelectionService()
    run = service.create_run(db, tenant_id="local", triggered_by="manual", user_id=1)
    run.status = "succeeded"
    run.report_body = "\n".join(
        [
            "# 智能选股综合系统 V8.0 专业投资决策报告",
            "- AData 个股资金流成功/降级：2/1",
            "- AData 个股资金流：部分降级（1 只按中性处理）",
        ]
    )
    db.add(run)
    db.commit()

    latest_response = client.get("/api/v1/smart-selection/latest")
    history_response = client.get("/api/v1/smart-selection/history")

    assert latest_response.status_code == 200
    assert history_response.status_code == 200

    latest_snapshot = latest_response.json()["snapshot"]
    history_runs = history_response.json()["runs"]

    assert latest_snapshot is not None
    assert latest_snapshot["id"] == run.id
    assert latest_snapshot["fund_flow_stats"] == {
        "available": True,
        "success_count": 2,
        "degraded_count": 1,
        "partial_degraded": True,
    }
    assert history_runs[0]["id"] == run.id
    assert history_runs[0]["fund_flow_stats"] == latest_snapshot["fund_flow_stats"]


def test_smart_selection_schedule_is_registered_and_visible_in_monitoring(client, monkeypatch) -> None:
    import app.api.monitoring as monitoring_api

    schedule = celery_app.conf.beat_schedule["run-smart-selection"]["schedule"]

    assert schedule._orig_hour == 20
    assert schedule._orig_minute == 0

    monkeypatch.setattr(monitoring_api, "get_persisted_task_stats", lambda: {})
    monkeypatch.setattr(monitoring_api, "get_task_runtime_stats", lambda: {})

    response = client.get("/api/v1/monitoring/async-tasks/summary")

    assert response.status_code == 200
    payload = response.json()
    task = next(item for item in payload["tasks"] if item["key"] == "run_smart_selection")
    assert task["schedule_seconds"] is None
    assert task["schedule_description"] == "0 20 * * *"


def test_institution_rating_pool_fetches_previous_day_when_latest_sample_is_small(monkeypatch) -> None:
    service = SmartSelectionService()
    fetched_urls: list[str] = []

    def row_html(code: str, name: str, rating_date: str, institution: str) -> str:
        return "\n".join(
            [
                code,
                name,
                "150",
                "买入",
                institution,
                "测试分析师",
                "测试行业",
                rating_date,
                "测试摘要",
            ]
        )

    pages = {
        1: row_html("600519", "贵州茅台", "2026-04-29", "测试证券A"),
        2: "\n".join(
            [
                row_html("300750", "宁德时代", "2026-04-28", "测试证券B"),
                row_html("000333", "美的集团", "2026-04-28", "测试证券C"),
            ]
        ),
        3: row_html("601318", "中国平安", "2026-04-27", "测试证券D"),
    }

    def fake_http_get(url: str, **kwargs):
        fetched_urls.append(url)
        page = int(url.rsplit("p=", 1)[1])
        return SimpleNamespace(text=pages[page])

    monkeypatch.setattr(service, "_http_get", fake_http_get)
    monkeypatch.setattr("app.smart_selection.service.time.sleep", lambda seconds: None)

    rows, stats = service._fetch_institution_rating_pool(
        {
            "institution_rating_pool": {
                "enabled": True,
                "source_url": "https://example.test/ratings?p=1",
                "pages": 5,
                "max_count": 10,
                "min_latest_date_rows": 2,
                "request_interval_ms": 0,
            }
        }
    )

    assert fetched_urls == [
        "https://example.test/ratings?p=1",
        "https://example.test/ratings?p=2",
        "https://example.test/ratings?p=3",
    ]
    assert {row["rating_date"] for row in rows} == {"2026-04-29", "2026-04-28"}
    assert {row["code"] for row in rows} == {"600519", "300750", "000333"}
    assert stats["latest_rating_date"] == "2026-04-29"
    assert stats["fallback_rating_date"] == "2026-04-28"
    assert stats["included_rating_dates"] == ["2026-04-29", "2026-04-28"]
    assert stats["latest_rating_date_rows"] == 1


def test_candidate_pool_uses_user_watchlist_instead_of_config_codes(db, monkeypatch) -> None:
    service = SmartSelectionService()
    _add_watchlist_item(db, "sh600519", sort_order=0, is_pinned=True)
    _add_watchlist_item(db, "sz000333", sort_order=1, is_pinned=False)

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        service,
        "_fetch_institution_rating_pool",
        lambda config: (
            [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "rating_date": "2026-04-27",
                    "institution": "测试机构",
                    "target_price": "150",
                },
                {
                    "code": "300750",
                    "name": "宁德时代",
                    "rating_date": "2026-04-27",
                    "institution": "测试机构",
                    "target_price": "280",
                },
            ],
            {"final_pool_size": 2},
        ),
    )

    def fake_get_spot_batch(codes: list[str], batch_size: int = 50) -> dict[str, dict]:
        captured["codes"] = list(codes)
        captured["batch_size"] = batch_size
        return {}

    monkeypatch.setattr(service, "_get_spot_batch", fake_get_spot_batch)

    spots, summary = service._build_candidate_pool(db, "local", _test_config_payload())

    assert spots == {}
    assert captured["codes"] == ["600519", "300750", "000333"]
    assert "111111" not in captured["codes"]
    assert "222222" not in captured["codes"]
    assert summary["watchlist_count"] == 2
    assert summary["institution_pool_count"] == 2
    assert summary["final_candidate_count"] == 0


def test_smart_selection_service_persists_report_and_items(db, monkeypatch) -> None:
    import app.smart_selection.service as smart_selection_service
    from app.market.history_storage import MarketDailyBarStorage

    service = SmartSelectionService()
    service.update_config(db, "local", SmartSelectionConfigUpdate(config_payload=_test_config_payload()))
    _add_watchlist_item(db, "sh600519", sort_order=0, is_pinned=True)

    monkeypatch.setattr(
        service,
        "_get_market_index",
        lambda: {
            "上证指数": {"price": 3300.0, "change": 1.2},
            "深证成指": {"price": 10000.0, "change": 0.9},
            "创业板指": {"price": 2100.0, "change": 1.6},
        },
    )
    monkeypatch.setattr(
        service,
        "_get_hot_sectors",
        lambda: [{"name": "白酒", "change": 3.4, "count": 12, "lead": "贵州茅台"}],
    )
    monkeypatch.setattr(
        service,
        "_fetch_institution_rating_pool",
        lambda config: ([
            {
                "code": "600519",
                "name": "贵州茅台",
                "rating": "买入",
                "rating_date": "2026-04-29",
                "institution": "测试证券",
                "institutions": ["测试证券", "样例证券"],
                "industry": "白酒",
                "industries": ["白酒"],
                "target_price": "150.00",
                "latest_price": "120.00",
                "change_pct": "+2.50%",
                "recommend_count": 2,
            }
        ], {"enabled": True, "final_pool_size": 1}),
    )
    monkeypatch.setattr(
        service,
        "_get_spot_batch",
        lambda codes, batch_size=50: {
            "600519": {
                "code": "600519",
                "name": "贵州茅台",
                "price": 120.0,
                "change": 2.5,
                "volume": 1_000_000,
                "amount": 8.6,
            }
        },
    )
    monkeypatch.setattr(service, "_get_kline_bars", lambda symbol, days=320: [])
    MarketDailyBarStorage(db).upsert_bars(_daily_bars_from_closes([100.0 + index for index in range(40)]), source="baostock", adjustflag="2")
    monkeypatch.setattr(
        service,
        "_analyze_tech",
        lambda bars, market_state, config: {
            "valid": True,
            "signals": ["均线多头共振", "主力资金流入"],
            "dim": {
                "trend": 20.0,
                "fund_flow": 25.0,
                "k_pattern": 22.0,
                "nine_turn": 10.0,
            },
            "ma20": 114.0,
            "boll_lower": 111.0,
            "boll_mid": 136.0,
            "atr_proxy": 2.0,
        },
    )
    monkeypatch.setattr(
        service,
        "_resolve_fund_flow_signal",
        lambda symbol: {
            "score": 19.0,
            "signals": ["AData主力净流入", "AData超大单流入"],
            "source": "adata",
            "status": {"code": "ok", "notes": None, "degraded": False},
            "raw": {
                "symbol": symbol,
                "trade_date": "2026-05-12",
                "main_net_inflow": 1.5e8,
                "super_large_net_inflow": 8.0e7,
                "large_net_inflow": 3.0e7,
                "medium_net_inflow": -1.0e7,
                "small_net_inflow": -2.0e7,
                "main_net_ratio": 8.6,
            },
            "score_detail": {
                "score": 19.0,
                "max_score": 25.0,
                "tone": "positive",
                "breakdown": {
                    "main_net_inflow": 11.0,
                    "super_large_net_inflow": 4.0,
                    "large_net_inflow": 3.0,
                    "main_net_ratio": 1.0,
                },
            },
        },
    )
    monkeypatch.setattr(smart_selection_service.DragonTigerAnalyzer, "fetch", lambda self: False)

    run = service.create_run(db, tenant_id="local", triggered_by="manual")
    executed = service.execute_run(db, run_id=run.id, task_id="smart-task-1", triggered_by="manual", tenant_id="local")
    latest = service.get_latest_snapshot(db, "local")

    assert executed.status.value == "succeeded"
    assert executed.candidate_pool_size == 1
    assert executed.recommendation_count == 1
    assert executed.report_body is not None
    assert executed.report_body.startswith("# 智能选股综合系统 V8.0 专业投资决策报告")
    assert "## 推荐股票" in executed.report_body
    assert "## 因子排名快照" in executed.report_body
    assert "因子画像" in executed.report_body
    assert "| 排名 | 股票名称 | 代码 | 综合评分 | 趋势均线 | 主力资金 | K线形态 | 神奇九转 | 龙虎榜 |" in executed.report_body
    assert "数据源：adata" in executed.report_body
    assert "主力净流入：+1.50 亿元" in executed.report_body
    assert "超大单净流入：+8000.00 万元" in executed.report_body
    assert latest.snapshot is not None
    assert latest.snapshot.id == executed.id
    assert len(latest.items) == 1
    assert latest.items[0].code == "600519"
    assert latest.items[0].target_price is not None and latest.items[0].target_price > latest.items[0].price
    assert latest.items[0].stop_loss_price is not None and latest.items[0].stop_loss_price < latest.items[0].price
    assert latest.items[0].raw_detail["timing"] == "STRONG BUY"
    assert latest.items[0].dimension_scores["fund_flow"] == 19.0
    assert latest.items[0].raw_detail["adata_fund_flow_source"] == "adata"
    assert latest.items[0].raw_detail["adata_fund_flow_status"]["code"] == "ok"
    assert latest.items[0].raw_detail["adata_fund_flow_score"]["score"] == 19.0
    assert latest.items[0].raw_detail["factor_context"]["bbi"]["rank"] == 1
    assert latest.items[0].raw_detail["factor_summary"]

    pool_items = db.query(SmartSelectionInstitutionPoolItem).filter(SmartSelectionInstitutionPoolItem.run_id == executed.id).all()
    assert len(pool_items) == 1
    assert pool_items[0].symbol == "sh600519"
    assert pool_items[0].recommend_count == 2
    assert pool_items[0].institutions == ["测试证券", "样例证券"]


def test_smart_selection_empty_report_reviews_near_miss_candidates(db, monkeypatch) -> None:
    import app.smart_selection.service as smart_selection_service

    service = SmartSelectionService()
    config = _test_config_payload()
    config["min_score"] = 90
    service.update_config(db, "local", SmartSelectionConfigUpdate(config_payload=config))
    _add_watchlist_item(db, "sh600519", sort_order=0, is_pinned=True)

    monkeypatch.setattr(service, "_get_market_index", lambda: {"上证指数": {"price": 3300.0, "change": 0.1}})
    monkeypatch.setattr(service, "_get_hot_sectors", lambda: [])
    monkeypatch.setattr(service, "_fetch_institution_rating_pool", lambda config: ([], {"enabled": False, "final_pool_size": 0}))
    monkeypatch.setattr(
        service,
        "_get_spot_batch",
        lambda codes, batch_size=50: {
            "600519": {"code": "600519", "name": "贵州茅台", "price": 120.0, "change": 1.2, "volume": 1_000_000, "amount": 8.6}
        },
    )
    monkeypatch.setattr(service, "_get_kline_bars", lambda symbol, days=320: _daily_bars_from_closes([100.0] * 40))
    monkeypatch.setattr(
        service,
        "_analyze_tech",
        lambda bars, market_state, config: {
            "valid": True,
            "signals": ["短期均线多头"],
            "dim": {"trend": 15.0, "fund_flow": 20.0, "k_pattern": 15.0, "nine_turn": 5.0},
            "ma20": 114.0,
            "boll_lower": 111.0,
            "boll_mid": 126.0,
            "atr_proxy": 3.0,
        },
    )
    monkeypatch.setattr(smart_selection_service.DragonTigerAnalyzer, "fetch", lambda self: False)

    run = service.create_run(db, tenant_id="local", triggered_by="manual")
    executed = service.execute_run(db, run_id=run.id, task_id="empty-task-1", triggered_by="manual", tenant_id="local")

    assert executed.recommendation_count == 0
    assert executed.report_body is not None
    assert "### 候选池复盘" in executed.report_body
    assert "### 未入选原因分布" in executed.report_body
    assert "### 接近入选观察标的" in executed.report_body
    assert "贵州茅台" in executed.report_body
    assert "综合分/风控阈值未达标" in executed.report_body
    assert "当前无符合专业风控要求的推荐标的" not in executed.report_body
    assert executed.summary is not None
    assert executed.summary.startswith("无推荐：候选 1 只，技术面有效 1 只")


def test_smart_selection_empty_report_explains_insufficient_kline(db, monkeypatch) -> None:
    import app.smart_selection.service as smart_selection_service

    service = SmartSelectionService()
    service.update_config(db, "local", SmartSelectionConfigUpdate(config_payload=_test_config_payload()))
    _add_watchlist_item(db, "sh600519", sort_order=0, is_pinned=True)

    monkeypatch.setattr(service, "_get_market_index", lambda: {"上证指数": {"price": 3300.0, "change": 0.1}})
    monkeypatch.setattr(service, "_get_hot_sectors", lambda: [])
    monkeypatch.setattr(service, "_fetch_institution_rating_pool", lambda config: ([], {"enabled": False, "final_pool_size": 0}))
    monkeypatch.setattr(
        service,
        "_get_spot_batch",
        lambda codes, batch_size=50: {
            "600519": {"code": "600519", "name": "贵州茅台", "price": 120.0, "change": 1.2, "volume": 1_000_000, "amount": 8.6}
        },
    )
    monkeypatch.setattr(service, "_get_kline_bars", lambda symbol, days=320: [])
    monkeypatch.setattr(smart_selection_service.DragonTigerAnalyzer, "fetch", lambda self: False)

    run = service.create_run(db, tenant_id="local", triggered_by="manual")
    executed = service.execute_run(db, run_id=run.id, task_id="empty-task-2", triggered_by="manual", tenant_id="local")

    assert executed.report_body is not None
    assert "K线不足 1 只" in executed.report_body
    assert "有效技术分析数量：0" in executed.report_body
    assert "补齐日线数据" in executed.report_body
    assert "技术面有效 0 只" in (executed.summary or "")


def test_smart_selection_empty_report_groups_basic_filter_reasons(db, monkeypatch) -> None:
    import app.smart_selection.service as smart_selection_service

    service = SmartSelectionService()
    service.update_config(db, "local", SmartSelectionConfigUpdate(config_payload=_test_config_payload()))
    _add_watchlist_item(db, "sh600000", sort_order=0, is_pinned=True)
    _add_watchlist_item(db, "sz000001", sort_order=1, is_pinned=False)
    _add_watchlist_item(db, "sh600111", sort_order=2, is_pinned=False)

    monkeypatch.setattr(service, "_get_market_index", lambda: {"上证指数": {"price": 3300.0, "change": 0.1}})
    monkeypatch.setattr(service, "_get_hot_sectors", lambda: [])
    monkeypatch.setattr(service, "_fetch_institution_rating_pool", lambda config: ([], {"enabled": False, "final_pool_size": 0}))
    monkeypatch.setattr(
        service,
        "_get_spot_batch",
        lambda codes, batch_size=50: {
            "600000": {"code": "600000", "name": "ST浦发", "price": 10.0, "change": 1.0, "volume": 1_000_000, "amount": 5.0},
            "000001": {"code": "000001", "name": "平安银行", "price": 2.0, "change": 1.0, "volume": 1_000_000, "amount": 5.0},
            "600111": {"code": "600111", "name": "北方稀土", "price": 20.0, "change": 1.0, "volume": 1_000_000, "amount": 0.5},
        },
    )
    monkeypatch.setattr(smart_selection_service.DragonTigerAnalyzer, "fetch", lambda self: False)

    run = service.create_run(db, tenant_id="local", triggered_by="manual")
    executed = service.execute_run(db, run_id=run.id, task_id="empty-task-3", triggered_by="manual", tenant_id="local")

    assert executed.report_body is not None
    assert "ST股票 1 只" in executed.report_body
    assert "价格区间不符 1 只" in executed.report_body
    assert "成交额不足 1 只" in executed.report_body
    assert "有效技术分析数量：0" in executed.report_body


def test_smart_selection_report_marks_dragon_tiger_degraded_when_sources_fail(db, monkeypatch) -> None:
    import app.smart_selection.service as smart_selection_service

    service = SmartSelectionService()
    service.update_config(db, "local", SmartSelectionConfigUpdate(config_payload=_test_config_payload()))
    _add_watchlist_item(db, "sh600519", sort_order=0, is_pinned=True)

    monkeypatch.setattr(service, "_get_market_index", lambda: {"上证指数": {"price": 3300.0, "change": 0.1}})
    monkeypatch.setattr(service, "_get_hot_sectors", lambda: [])
    monkeypatch.setattr(service, "_fetch_institution_rating_pool", lambda config: ([], {"enabled": False, "final_pool_size": 0}))
    monkeypatch.setattr(
        service,
        "_get_spot_batch",
        lambda codes, batch_size=50: {
            "600519": {"code": "600519", "name": "贵州茅台", "price": 120.0, "change": 1.2, "volume": 1_000_000, "amount": 8.6}
        },
    )
    monkeypatch.setattr(service, "_get_kline_bars", lambda symbol, days=320: _daily_bars_from_closes([100.0] * 40))
    monkeypatch.setattr(
        service,
        "_analyze_tech",
        lambda bars, market_state, config: {
            "valid": True,
            "signals": ["短期均线多头"],
            "dim": {"trend": 15.0, "fund_flow": 20.0, "k_pattern": 15.0, "nine_turn": 5.0},
            "ma20": 114.0,
            "boll_lower": 111.0,
            "boll_mid": 126.0,
            "atr_proxy": 3.0,
        },
    )
    monkeypatch.setattr(
        service,
        "_resolve_fund_flow_signal",
        lambda symbol: {
            "score": 0.0,
            "signals": ["AData资金流数据暂不可用，本次按中性处理"],
            "source": "adata",
            "status": {"code": "dependency_error", "notes": "adata:dependency_error", "degraded": True},
            "raw": {
                "symbol": symbol,
                "trade_date": None,
                "main_net_inflow": None,
                "super_large_net_inflow": None,
                "large_net_inflow": None,
                "medium_net_inflow": None,
                "small_net_inflow": None,
                "main_net_ratio": None,
            },
            "score_detail": {
                "score": 0.0,
                "max_score": 25.0,
                "tone": "neutral",
                "breakdown": {
                    "main_net_inflow": 0.0,
                    "super_large_net_inflow": 0.0,
                    "large_net_inflow": 0.0,
                    "main_net_ratio": 0.0,
                },
            },
        },
    )
    monkeypatch.setattr(
        smart_selection_service,
        "DragonTigerAnalyzer",
        lambda config: type(
            "StubAnalyzer",
            (),
            {
                "enabled": False,
                "source_name": None,
                "fallback_used": False,
                "status": "dependency_error",
                "status_note": "adata:dependency_error; akshare:empty_response",
                "black_seats": [],
                "red_seats": [],
                "black_stocks": {},
                "red_stocks": {},
                "fetch": lambda self: False,
                "classify": lambda self, stock_name: smart_selection_service.DragonTigerSignal(tag="N/A", score_delta=0.0, signals=[], detail={}),
            },
        )(),
    )

    run = service.create_run(db, tenant_id="local", triggered_by="manual")
    executed = service.execute_run(db, run_id=run.id, task_id="lhb-degraded-1", triggered_by="manual", tenant_id="local")

    assert executed.report_body is not None
    assert "龙虎榜数据暂不可用，策略按降级模式执行" in executed.report_body
    assert "降级原因：dependency_error:adata:dependency_error; akshare:empty_response" in executed.report_body
    assert "资金流数据暂不可用，本次按中性处理" in executed.report_body
    assert "AData 个股资金流成功/降级：0/1" in executed.report_body
    assert "AData 个股资金流：部分降级（1 只按中性处理）" in executed.report_body


def test_smart_selection_service_marks_failed_runs(db, monkeypatch) -> None:
    service = SmartSelectionService()
    service.update_config(db, "local", SmartSelectionConfigUpdate(config_payload=_test_config_payload()))
    monkeypatch.setattr(service, "_get_market_index", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    run = service.create_run(db, tenant_id="local", triggered_by="manual")

    with pytest.raises(RuntimeError, match="boom"):
        service.execute_run(db, run_id=run.id, task_id="smart-task-failed", triggered_by="manual", tenant_id="local")

    db.refresh(run)
    assert run.status.value == "failed"
    assert run.error_message == "boom"


def test_run_smart_selection_task_executes_service(client, monkeypatch) -> None:
    import app.tasks.smart_selection_tasks as smart_selection_tasks

    monkeypatch.setattr(
        smart_selection_tasks.SmartSelectionService,
        "execute_run",
        lambda self, db, run_id=None, task_id=None, triggered_by="system", tenant_id="local": SimpleNamespace(
            id=11,
            recommendation_count=3,
        ),
    )

    result = smart_selection_tasks.run_smart_selection_task(run_id=11, triggered_by="manual", tenant_id="local")

    assert result["status"] == "completed"
    assert result["task"] == "run_smart_selection"
    assert result["run_id"] == 11
    assert result["recommendation_count"] == 3


def test_score_enhancer_preserves_base_score_and_explains_delta() -> None:
    from app.smart_selection.scoring_enhancement import SCORE_VERSION, SmartSelectionScoreEnhancer

    result = SmartSelectionScoreEnhancer.enhance(
        base_score=70.0,
        dimension_scores={"trend": 20.0, "fund_flow": 25.0, "k_pattern": 20.0, "nine_turn": 10.0, "lhb": 5.0, "hot_sectors": 5.0, "market": 6.0, "liquidity": 8.0},
        risk_reward=2.0,
        market_state={"regime": "strong"},
        config={},
    )

    assert result["score_version"] == SCORE_VERSION
    assert result["base_score"] == 70.0
    assert result["enhanced_score"] > result["base_score"]
    assert result["score_explain"]["risk_reward"] > 0
    assert result["factor_weights"]["trend"] == 1.1


def test_smart_selection_run_persists_enhanced_score_metadata(db, monkeypatch) -> None:
    import app.smart_selection.service as smart_selection_service

    service = SmartSelectionService()
    config = _test_config_payload()
    service.update_config(db, "local", SmartSelectionConfigUpdate(config_payload=config))
    _add_watchlist_item(db, "sh600519", sort_order=0, is_pinned=True)

    monkeypatch.setattr(service, "_get_market_index", lambda: {"上证指数": {"price": 3300.0, "change": 1.0}})
    monkeypatch.setattr(service, "_get_hot_sectors", lambda: [])
    monkeypatch.setattr(service, "_fetch_institution_rating_pool", lambda config: ([], {"enabled": False, "final_pool_size": 0}))
    monkeypatch.setattr(
        service,
        "_get_spot_batch",
        lambda codes, batch_size=50: {
            "600519": {"code": "600519", "name": "贵州茅台", "price": 120.0, "change": 2.5, "volume": 1_000_000, "amount": 8.6}
        },
    )
    monkeypatch.setattr(service, "_get_kline_bars", lambda symbol, days=320: [])
    monkeypatch.setattr(
        service,
        "_analyze_tech",
        lambda bars, market_state, config: {
            "valid": True,
            "signals": ["均线多头共振", "主力资金流入"],
            "dim": {"trend": 20.0, "fund_flow": 25.0, "k_pattern": 22.0, "nine_turn": 10.0},
            "ma20": 114.0,
            "boll_lower": 111.0,
            "boll_mid": 136.0,
            "atr_proxy": 2.0,
        },
    )
    monkeypatch.setattr(
        service,
        "_resolve_fund_flow_signal",
        lambda symbol: {
            "score": 18.0,
            "signals": ["AData主力净流入"],
            "source": "adata",
            "status": {"code": "ok", "notes": None, "degraded": False},
            "raw": {
                "symbol": symbol,
                "trade_date": "2026-05-12",
                "main_net_inflow": 1.1e8,
                "super_large_net_inflow": 4.8e7,
                "large_net_inflow": 2.2e7,
                "medium_net_inflow": -0.8e7,
                "small_net_inflow": -1.2e7,
                "main_net_ratio": 7.5,
            },
            "score_detail": {
                "score": 18.0,
                "max_score": 25.0,
                "tone": "positive",
                "breakdown": {
                    "main_net_inflow": 11.0,
                    "super_large_net_inflow": 2.0,
                    "large_net_inflow": 3.0,
                    "main_net_ratio": 2.0,
                },
            },
        },
    )
    monkeypatch.setattr(smart_selection_service.DragonTigerAnalyzer, "fetch", lambda self: False)

    run = service.create_run(db, tenant_id="local", triggered_by="manual")
    executed = service.execute_run(db, run_id=run.id, task_id="enhanced-task-1", triggered_by="manual", tenant_id="local")
    latest = service.get_latest_snapshot(db, "local")

    assert executed.status.value == "succeeded"
    item = latest.items[0]
    assert item.enhanced_score is not None
    assert item.score_enhancement["base_score"] == item.score
    assert item.raw_detail["score_enhancement"]["score_version"] == "smart-selection-enhanced/v1"
    assert "增强评分" in (executed.report_body or "")


def test_smart_selection_evaluation_api_reports_forward_returns(client, db) -> None:
    from app.market.history_storage import MarketDailyBarStorage
    from app.models.smart_selection_item import SmartSelectionItem
    from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus

    run = SmartSelectionRun(tenant_id="local", status=SmartSelectionRunStatus.SUCCEEDED, triggered_by="manual", recommendation_count=1, candidate_pool_size=1)
    db.add(run)
    db.flush()
    item = SmartSelectionItem(
        run_id=run.id,
        symbol="sh600519",
        code="600519",
        name="贵州茅台",
        score=80.0,
        price=100.0,
        target_price=112.0,
        stop_loss_price=95.0,
        tags=[],
        reason="测试",
        dimension_scores={"trend": 20.0},
        raw_detail={"score_enhancement": {"enhanced_score": 84.0}},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db.add(item)
    db.commit()
    bars = []
    for offset, close in enumerate([100.0, 106.0, 113.0, 108.0, 110.0, 112.0]):
        bar = DailyBarSnapshot(
            symbol="sh600519",
            trade_date=date(2026, 1, 1) + timedelta(days=offset),
            open_price=close,
            close_price=close,
            high_price=close + 1,
            low_price=close - 1,
            volume=1_000_000,
        )
        bars.append(bar)
    MarketDailyBarStorage(db).upsert_bars(bars, source="baostock", adjustflag="2")

    response = client.get(f"/api/v1/smart-selection/runs/{run.id}/evaluation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_count"] == 1
    assert payload["items"][0]["enhanced_score"] == 84.0
    assert payload["items"][0]["horizons"]["5d"]["forward_return_pct"] == 12.0
    assert payload["items"][0]["horizons"]["5d"]["target_hit"] is True
    assert payload["summary"]["5d"]["win_rate_pct"] == 100.0


def test_smart_selection_factor_rank_api_returns_local_factor_scores(client, db) -> None:
    from app.market.history_storage import MarketDailyBarStorage

    storage = MarketDailyBarStorage(db)
    storage.upsert_bars(_daily_bars_from_closes([100.0 + index for index in range(40)]), source="baostock", adjustflag="2")

    response = client.post(
        "/api/v1/smart-selection/factors/rank",
        json={"symbols": ["sh600519"], "factor": "bbi", "limit": 40},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["factor"] == "bbi"
    assert payload["items"][0]["symbol"] == "sh600519"
    assert payload["items"][0]["rank"] == 1
    assert payload["items"][0]["missing_reason"] is None
    assert payload["items"][0]["computable"] is True
    assert payload["items"][0]["missing_ratio"] == 0.0
    assert payload["items"][0]["source_fields"] == ["close_price"]


def test_smart_selection_factor_context_keeps_api_field_names_and_does_not_override_result_fields(db) -> None:
    from app.market.history_storage import MarketDailyBarStorage

    service = SmartSelectionService()
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars(_daily_bars_from_closes([100.0 + index for index in range(40)]), source="baostock", adjustflag="2")

    context = service.build_factor_context(db, ["sh600519"], factors=("bbi", "cci"), limit=40)
    assert context["sh600519"]["bbi"]["computable"] is True
    assert context["sh600519"]["bbi"]["missing_ratio"] == 0.0
    assert context["sh600519"]["bbi"]["source_fields"] == ["close_price"]
    assert context["sh600519"]["cci"]["source_fields"] == ["close_price", "high_price", "low_price"]
    assert "missing_reason" in context["sh600519"]["bbi"]

    result = {"symbol": "sh600519", "close_price": 123.45, "factor_context": {"legacy": "keep"}}
    service._attach_factor_context([result], context)

    assert result["close_price"] == 123.45
    assert "bbi" in result["factor_context"]
    assert result["factor_context"]["bbi"]["source_fields"] == ["close_price"]
    assert result["factor_summary"]


def test_smart_selection_factor_rank_requires_symbols(client) -> None:
    missing_response = client.post(
        "/api/v1/smart-selection/factors/rank",
        json={"factor": "bbi", "limit": 40},
    )
    empty_response = client.post(
        "/api/v1/smart-selection/factors/rank",
        json={"symbols": [], "factor": "bbi", "limit": 40},
    )

    assert missing_response.status_code == 422
    assert empty_response.status_code == 422
