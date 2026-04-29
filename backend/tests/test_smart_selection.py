from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.celery_app import celery_app
from app.models.watchlist import WatchlistItem
from app.market.providers.base import DailyBarSnapshot
from app.schemas.smart_selection import SmartSelectionConfigUpdate
from app.smart_selection.service import SmartSelectionService


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
        lambda config: ([], {"enabled": False, "final_pool_size": 0}),
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
    assert "| 排名 | 股票名称 | 代码 | 综合评分 | 趋势均线 | 主力资金 | K线形态 | 神奇九转 | 龙虎榜 |" in executed.report_body
    assert latest.snapshot is not None
    assert latest.snapshot.id == executed.id
    assert len(latest.items) == 1
    assert latest.items[0].code == "600519"
    assert latest.items[0].target_price is not None and latest.items[0].target_price > latest.items[0].price
    assert latest.items[0].stop_loss_price is not None and latest.items[0].stop_loss_price < latest.items[0].price
    assert latest.items[0].raw_detail["timing"] == "STRONG BUY"


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
