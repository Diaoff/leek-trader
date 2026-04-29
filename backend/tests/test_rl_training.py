from datetime import date, timedelta

from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot
from app.models.watchlist import WatchlistItem
from app.models.smart_selection_institution_pool_item import SmartSelectionInstitutionPoolItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus


def _bar(symbol: str, trade_date: date, close_price: float) -> DailyBarSnapshot:
    return DailyBarSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        open_price=close_price,
        close_price=close_price,
        high_price=close_price * 1.01,
        low_price=close_price * 0.99,
        volume=1000000.0,
        turnover=close_price * 1000000.0,
        trade_status=1,
        is_st=False,
    )


def _seed_daily_bars(db, symbol: str, *, days: int = 36) -> None:
    start = date(2026, 1, 1)
    bars = [_bar(symbol, start + timedelta(days=index), 10 + index * 0.1) for index in range(days)]
    MarketDailyBarStorage(db).upsert_bars(bars, source="baostock", adjustflag="2")


def test_resolve_rl_training_symbols_from_watchlist(db, client) -> None:
    db.add(WatchlistItem(symbol="sh600519"))
    db.commit()

    response = client.post("/api/v1/market/rl/training/resolve", json={"scope": "watchlist", "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["symbols"][0]["symbol"] == "sh600519"
    assert payload["symbols"][0]["name"] == "贵州茅台"


def test_train_rl_model_creates_file_artifact(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    _seed_daily_bars(db, "sh600519")

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "测试 RL 模型",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "episodes": 2,
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "测试 RL 模型"
    assert payload["algorithm"] == "tabular_q_learning"
    assert payload["metrics"]["evaluated_symbol_count"] == 1
    assert payload["training"]["state_count"] > 0
    assert (tmp_path / payload["model_id"] / "model.json").exists()

    list_response = client.get("/api/v1/market/rl/models")
    assert list_response.status_code == 200
    assert list_response.json()["models"][0]["model_id"] == payload["model_id"]


def test_rl_strategy_can_load_validated_trained_model(tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module
    from app.strategy.strategies.rl_trading import RLTradingStrategy

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    registry = training_module.RLModelRegistry()
    registry.save({
        "model_id": "test-model",
        "name": "测试模型",
        "status": "validated",
        "algorithm": "tabular_q_learning",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "scope": "manual",
        "symbols": [],
        "config": {},
        "training": {
            "action_space": [0.0, 0.25, 0.5, 0.75, 1.0],
            "q_table": {
                "up|flat|normal|low": [0.0, 0.1, 0.2, 0.3, 1.0]
            },
        },
        "metrics": {},
        "evaluations": [],
        "dataset_manifest": {},
    })
    bars = [_bar("sh600519", date(2026, 1, 1) + timedelta(days=index), 10 + index * 0.1) for index in range(30)]

    signal = RLTradingStrategy().evaluate(
        "sh600519",
        bars,
        {"rl_policy_mode": "trained_model", "model_id": "test-model", "ma_short_window": 5, "ma_long_window": 20},
    )

    assert signal["trigger_reason"] == "rl_trained_model_action"
    assert signal["rl_action"]["policy_mode"] == "trained_model"
    assert signal["signal"] in {"buy", "hold", "sell"}


def test_rl_training_job_reports_progress_and_result(client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    monkeypatch.setattr(training_module.RLTrainingJobRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path / "jobs") or self.root.mkdir(parents=True, exist_ok=True))

    def fake_train(self, **kwargs):
        progress = kwargs.get("progress_callback")
        if progress:
            progress(1, 2, "fake half")
            progress(2, 2, "fake done")
        return {
            "model_id": "job-model",
            "name": kwargs["model_name"],
            "status": "validated",
            "algorithm": "tabular_q_learning",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "scope": kwargs["scope"],
            "symbols": [],
            "config": {},
            "training": {},
            "metrics": {"trade_count": 1},
            "validation": {"passed": True, "blockers": []},
            "evaluations": [],
            "dataset_manifest": {},
        }

    monkeypatch.setattr(training_module.RLTrainingService, "train", fake_train)

    submit = client.post(
        "/api/v1/market/rl/training/jobs",
        json={
            "model_name": "异步测试模型",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "episodes": 2,
        },
    )

    assert submit.status_code == 200
    job_id = submit.json()["job_id"]
    latest = submit.json()
    for _ in range(50):
        status = client.get(f"/api/v1/market/rl/training/jobs/{job_id}")
        assert status.status_code == 200
        latest = status.json()
        if latest["status"] in {"succeeded", "failed"}:
            break

    assert latest["status"] == "succeeded", latest
    assert latest["progress_pct"] == 100.0
    assert latest["model_id"] == "job-model"
    assert latest["model"]["name"] == "异步测试模型"


def test_rl_model_activation_requires_validation(client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    registry = training_module.RLModelRegistry()
    registry.save({
        "model_id": "draft-model",
        "name": "未验证模型",
        "status": "draft",
        "algorithm": "tabular_q_learning",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "scope": "manual",
        "symbols": [],
        "config": {},
        "training": {},
        "metrics": {"trade_count": 0},
        "validation": {"passed": False, "blockers": ["no_trades"]},
        "evaluations": [],
        "dataset_manifest": {},
    })

    response = client.patch("/api/v1/market/rl/models/draft-model/status", json={"status": "active"})

    assert response.status_code == 422
    assert response.json()["detail"] == "model must pass validation before activation"


def test_resolve_rl_training_symbols_prefers_institution_pool_recommend_count(db, client) -> None:
    run = SmartSelectionRun(tenant_id="local", status=SmartSelectionRunStatus.SUCCEEDED, triggered_by="manual")
    db.add(run)
    db.flush()
    db.add_all([
        SmartSelectionInstitutionPoolItem(
            run_id=run.id,
            symbol="sh600519",
            code="600519",
            name="贵州茅台",
            rating_date="2026-04-29",
            recommend_count=3,
            institutions=["A证券", "B证券", "C证券"],
            industries=["白酒"],
        ),
        SmartSelectionInstitutionPoolItem(
            run_id=run.id,
            symbol="sz300750",
            code="300750",
            name="宁德时代",
            rating_date="2026-04-29",
            recommend_count=1,
            institutions=["A证券"],
            industries=["电池"],
        ),
    ])
    db.commit()

    response = client.post("/api/v1/market/rl/training/resolve", json={"scope": "smart_selection", "limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert [item["symbol"] for item in payload["symbols"]] == ["sh600519", "sz300750"]
    assert payload["symbols"][0]["source"] == "institution_recommendation:3"


def test_initialize_database_creates_institution_pool_table(db) -> None:
    from sqlalchemy import inspect

    import app.core.db as db_module
    from app.db.init_db import initialize_database

    initialize_database()

    assert inspect(db_module.engine).has_table("smart_selection_institution_pool_items")
