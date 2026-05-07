from datetime import date, timedelta

from app.market.baostock_sync_service import BaoStockSyncFailure, BaoStockSyncResult
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


def _install_fake_ppo_training(monkeypatch, training_module) -> None:
    class FakePPOTrainer:
        def __init__(self, config):
            self.config = config

        def train(self, records_by_symbol, *, model_path, progress_callback=None, dataset_split=None):
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("fake policy", encoding="utf-8")
            if progress_callback:
                progress_callback(1, 1, "fake ppo done", ["ok"])
            train_symbol_count = len(dataset_split.train) if dataset_split is not None else len(records_by_symbol)
            validation_symbol_count = len(dataset_split.validation) if dataset_split is not None else len(records_by_symbol)
            return {
                "algorithm": "ppo_trading",
                "policy_path": model_path.name,
                "observation_size": 28,
                "observation_version": "ppo-observation/v2",
                "observation_features": ["return_since_start"],
                "action_space": [0.0, 0.25, 0.5, 0.75, 1.0],
                "total_timesteps": self.config.total_timesteps,
                "train_symbol_count": train_symbol_count,
                "validation_symbol_count": validation_symbol_count,
                "splits": dataset_split.metadata if dataset_split is not None else {},
                "hyperparameters": {"reward_mode": self.config.reward_mode},
            }

    class FakePolicyModel:
        def predict(self, observation, deterministic=True):
            return [4], None

    monkeypatch.setattr(training_module, "PPOTradingTrainer", FakePPOTrainer)
    monkeypatch.setattr(training_module, "load_ppo_model", lambda path: FakePolicyModel())
    monkeypatch.setattr(training_module, "predict_ppo_action", lambda artifact, records, model=None: {"action_index": 4, "action_type": "buy", "target_position_pct": 1.0})


def test_resolve_rl_training_symbols_from_watchlist(db, client) -> None:
    db.add(WatchlistItem(symbol="sh600519"))
    db.commit()

    response = client.post("/api/v1/market/rl/training/resolve", json={"scope": "watchlist", "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["symbols"][0]["symbol"] == "sh600519"
    assert payload["symbols"][0]["name"] == "贵州茅台"


def test_ppo_observation_features_are_stable_and_clipped(monkeypatch) -> None:
    import app.quant.ppo_training as ppo_module

    class Box:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Discrete:
        def __init__(self, value):
            self.value = value

    class Env:
        def reset(self, *, seed=None):
            return None

    monkeypatch.setattr(ppo_module, "gym", type("Gym", (), {"Env": Env}))
    monkeypatch.setattr(ppo_module, "spaces", type("Spaces", (), {"Box": Box, "Discrete": Discrete}))
    records = [
        {
            "symbol": "sh600519",
            "trade_date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "open_price": 10 + index * 0.1,
            "close_price": 10 + index * 0.1,
            "high_price": 10 + index * 0.1 + 0.2,
            "low_price": 10 + index * 0.1 - 0.2,
            "volume": 1000000 + index,
            "turnover": None,
            "turnover_rate": None,
            "trade_status": None,
        }
        for index in range(30)
    ]

    env = ppo_module.MultiStockTradingEnv({"sh600519": records}, ppo_module.PPOTrainingConfig())
    observation = env._observation()

    assert len(observation) == ppo_module.PPO_OBSERVATION_SIZE
    assert ppo_module.PPO_OBSERVATION_SIZE == len(ppo_module.PPO_OBSERVATION_FEATURES)
    assert observation.min() >= -10
    assert observation.max() <= 10


def test_ppo_split_records_are_strictly_out_of_sample() -> None:
    from app.quant.ppo_training import split_records_by_symbol

    records = [
        {"symbol": "sh600519", "trade_date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(), "close_price": 10 + index}
        for index in range(20)
    ]

    split = split_records_by_symbol({"sh600519": records}, 0.75, min_validation_bars=4)

    assert split.train["sh600519"][-1]["trade_date"] < split.validation["sh600519"][0]["trade_date"]
    assert split.metadata["sh600519"]["included_in_training"] is True
    assert split.metadata["sh600519"]["validation_bars"] >= 4


def test_rl_training_defaults_match_conservative_requirements() -> None:
    from app.quant.ppo_training import PPOTrainingConfig
    from app.quant.simulator import RLEpisodeConfig
    from app.schemas.market import RLEpisodeSimulateRequest, RLTrainingRequest

    episode_config = RLEpisodeConfig()
    ppo_config = PPOTrainingConfig()
    simulate_request = RLEpisodeSimulateRequest(symbols=["sh600519"])
    training_request = RLTrainingRequest()

    assert episode_config.reward_mode == "risk_adjusted_excess_return"
    assert ppo_config.reward_mode == "risk_adjusted_excess_return"
    assert simulate_request.reward_mode == "risk_adjusted_excess_return"
    assert training_request.reward_mode == "risk_adjusted_excess_return"
    assert episode_config.max_position_pct == 0.6
    assert ppo_config.max_position_pct == 0.6
    assert simulate_request.max_position_pct == 0.6
    assert training_request.max_position_pct == 0.6
    assert episode_config.drawdown_penalty_coef == 0.06
    assert ppo_config.drawdown_penalty_coef == 0.06
    assert simulate_request.drawdown_penalty_coef == 0.06
    assert training_request.drawdown_penalty_coef == 0.06
    assert ppo_config.learning_rate == 0.00031
    assert training_request.ppo_learning_rate == 0.00031


def test_ppo_drawdown_penalty_reward_uses_coefficient_and_participation(monkeypatch) -> None:
    import app.quant.ppo_training as ppo_module

    class Box:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Discrete:
        def __init__(self, value):
            self.value = value

    class Env:
        def reset(self, *, seed=None):
            return None

    monkeypatch.setattr(ppo_module, "gym", type("Gym", (), {"Env": Env}))
    monkeypatch.setattr(ppo_module, "spaces", type("Spaces", (), {"Box": Box, "Discrete": Discrete}))

    records = [
        {
            "symbol": "sh600519",
            "trade_date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "open_price": 10.0,
            "close_price": 10.0,
            "high_price": 10.0,
            "low_price": 10.0,
            "volume": 1000000,
            "turnover": None,
            "turnover_rate": None,
            "trade_status": None,
        }
        for index in range(2)
    ]
    config = ppo_module.PPOTrainingConfig(reward_mode="drawdown_penalty", drawdown_penalty_coef=0.2)
    env = ppo_module.MultiStockTradingEnv({"sh600519": records}, config)

    reward = env._reward(
        portfolio_return=-0.02,
        benchmark_return=0.0,
        drawdown_pct=10.0,
        position_pct=0.6,
    )

    assert round(reward, 5) == -0.03994
    assert env.last_reward_breakdown["drawdown_penalty"] == 0.02
    assert env.last_reward_breakdown["active_position_reward"] == 0.00006


def test_ppo_empty_training_env_uses_actionable_error(monkeypatch) -> None:
    import pytest
    import app.quant.ppo_training as ppo_module

    class Box:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Discrete:
        def __init__(self, value):
            self.value = value

    class Env:
        def reset(self, *, seed=None):
            return None

    monkeypatch.setattr(ppo_module, "gym", type("Gym", (), {"Env": Env}))
    monkeypatch.setattr(ppo_module, "spaces", type("Spaces", (), {"Box": Box, "Discrete": Discrete}))

    with pytest.raises(ValueError) as error:
        ppo_module.MultiStockTradingEnv({"sh600519": []}, ppo_module.PPOTrainingConfig())

    message = str(error.value)
    assert "two daily bars" not in message
    assert "widen the training date range" in message


def test_train_ppo_model_creates_policy_artifact(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    _seed_daily_bars(db, "sh600519", days=45)

    class FakePPOTrainer:
        def __init__(self, config):
            self.config = config

        def train(self, records_by_symbol, *, model_path, progress_callback=None, dataset_split=None):
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text("fake policy", encoding="utf-8")
            if progress_callback:
                progress_callback(1, 1, "fake ppo done", ["ok"])
            return {
                "algorithm": "ppo_trading",
                "policy_path": model_path.name,
                "observation_size": 28,
                "observation_version": "ppo-observation/v2",
                "observation_features": ["return_since_start"],
                "action_space": [0.0, 0.25, 0.5, 0.75, 1.0],
                "total_timesteps": self.config.total_timesteps,
                "train_symbol_count": len(records_by_symbol),
                "validation_symbol_count": len(records_by_symbol),
                "splits": {},
                "hyperparameters": {"reward_mode": self.config.reward_mode},
            }

    class FakePolicyModel:
        def predict(self, observation, deterministic=True):
            return [4], None

    monkeypatch.setattr(training_module, "PPOTradingTrainer", FakePPOTrainer)
    monkeypatch.setattr(training_module, "load_ppo_model", lambda path: FakePolicyModel())
    monkeypatch.setattr(training_module, "predict_ppo_action", lambda artifact, records, model=None: {"action_index": 4, "action_type": "buy", "target_position_pct": 1.0})

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "PPO 测试模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "total_timesteps": 1000,
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["algorithm"] == "ppo_trading"
    assert payload["training"]["policy_path"] == "policy.zip"
    assert payload["training"]["total_timesteps"] == 1000
    assert payload["training"]["observation_version"] == "ppo-observation/v2"
    assert "splits" in payload
    assert "validation" in payload["metrics"].get("splits", {})
    assert (tmp_path / payload["model_id"] / "policy.zip").exists()


def test_train_ppo_model_reuses_service_dataset_split(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.ppo_training as ppo_module
    import app.quant.training as training_module

    class Box:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Discrete:
        def __init__(self, value):
            self.value = value

    class Env:
        def reset(self, *, seed=None):
            return None

    class FakePPO:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def learn(self, *, total_timesteps, callback=None):
            if callback is not None:
                callback.num_timesteps = total_timesteps
                callback._on_step()

        def save(self, path):
            with open(path, "w", encoding="utf-8") as output:
                output.write("fake policy")

    class FakePolicyModel:
        def predict(self, observation, deterministic=True):
            return [4], None

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    monkeypatch.setattr(ppo_module, "gym", type("Gym", (), {"Env": Env}))
    monkeypatch.setattr(ppo_module, "spaces", type("Spaces", (), {"Box": Box, "Discrete": Discrete}))
    monkeypatch.setattr(ppo_module, "PPO", FakePPO)
    monkeypatch.setattr(ppo_module, "split_records_by_symbol", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("trainer must not split again")))
    monkeypatch.setattr(training_module, "load_ppo_model", lambda path: FakePolicyModel())
    monkeypatch.setattr(training_module, "predict_ppo_action", lambda artifact, records, model=None: {"action_index": 4, "action_type": "buy", "target_position_pct": 1.0})
    _seed_daily_bars(db, "sh600519", days=45)

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "复用切分 PPO 模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "total_timesteps": 1000,
            "limit": 5,
        },
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["training"]["train_symbol_count"] == 1
    assert payload["training"]["validation_symbol_count"] == 1
    assert payload["training"]["splits"]["sh600519"]["included_in_training"] is True


def test_train_rl_model_creates_file_artifact(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module
    _install_fake_ppo_training(monkeypatch, training_module)

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    _seed_daily_bars(db, "sh600519")

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "测试 RL 模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "测试 RL 模型"
    assert payload["algorithm"] == "ppo_trading"
    assert payload["metrics"]["evaluated_symbol_count"] == 1
    assert payload["metrics"]["candidate_symbol_count"] == 1
    assert payload["metrics"]["trainable_symbol_count"] == 1
    assert payload["metrics"]["trainable_symbol_ratio"] == 1.0
    assert payload["metrics"]["training_transition_count"] == payload["training"]["total_timesteps"]
    assert "benchmark_return_pct" in payload["evaluations"][0]
    assert "trade_details_sample" in payload["evaluations"][0]
    assert payload["training"]["policy_path"] == "policy.zip"
    assert (tmp_path / payload["model_id"] / "model.json").exists()

    list_response = client.get("/api/v1/market/rl/models")
    assert list_response.status_code == 200
    assert list_response.json()["models"][0]["model_id"] == payload["model_id"]


def test_train_rl_model_rejects_tabular_q_learning(client) -> None:
    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "旧 Q-learning 模型",
            "algorithm": "tabular_q_learning",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "limit": 5,
        },
    )

    assert response.status_code == 422


def test_train_rl_model_syncs_symbols_with_partial_local_coverage(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module
    _install_fake_ppo_training(monkeypatch, training_module)

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    _seed_daily_bars(db, "sh600519")
    sync_calls = []

    def fake_sync(self, *, symbols, start_date, end_date, adjustflag="2", incremental=False, progress_callback=None):
        sync_calls.append(list(symbols))
        if progress_callback:
            progress_callback(1, len(symbols), "正在获取 sz000001 日线", ["日期范围：2026-01-01 ~ 2026-02-20"])
        for symbol in symbols:
            _seed_daily_bars(db, symbol, days=36)
        return BaoStockSyncResult(
            status="completed",
            source="baostock",
            adjustflag=adjustflag,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            requested_symbols=symbols,
            incremental=incremental,
            succeeded_symbols=symbols,
            bars_upserted=72,
        )

    monkeypatch.setattr(training_module.BaoStockHistorySyncService, "sync_history", fake_sync)

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "部分补齐 RL 模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519", "sz000001", "sz000002"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert sync_calls == [["sz000001", "sz000002"]]
    assert payload["metrics"]["candidate_symbol_count"] == 3
    assert payload["metrics"]["trainable_symbol_count"] == 3
    assert payload["metrics"]["trainable_symbol_ratio"] == 1.0


def test_train_rl_model_auto_syncs_baostock_history_when_local_bars_missing(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module
    _install_fake_ppo_training(monkeypatch, training_module)

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    sync_calls = []

    def fake_sync(self, *, symbols, start_date, end_date, adjustflag="2", incremental=False, progress_callback=None):
        sync_calls.append({
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "adjustflag": adjustflag,
            "incremental": incremental,
        })
        if progress_callback:
            progress_callback(1, len(symbols), "正在获取 sh600519 日线", ["日期范围：2026-01-01 ~ 2026-02-20"])
        _seed_daily_bars(db, symbols[0], days=36)
        return None

    monkeypatch.setattr(training_module.BaoStockHistorySyncService, "sync_history", fake_sync)

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "自动同步 RL 模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    assert sync_calls == [{
        "symbols": ["sh600519"],
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 2, 20),
        "adjustflag": "2",
        "incremental": True,
    }]
    assert response.json()["metrics"]["evaluated_symbol_count"] == 1


def test_train_rl_model_reports_baostock_sync_failure_as_validation_error(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))

    def fail_sync(self, **kwargs):
        raise RuntimeError("baostock unavailable")

    monkeypatch.setattr(training_module.BaoStockHistorySyncService, "sync_history", fail_sync)

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "同步失败 RL 模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "limit": 5,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "failed to sync BaoStock history for RL training: baostock unavailable"


def test_rl_training_fallback_provider_order_prefers_tencent() -> None:
    import app.quant.training as training_module

    assert [provider.name for provider in training_module.FALLBACK_HISTORY_PROVIDERS] == ["tencent", "sina", "eastmoney"]


def test_large_scope_with_low_trainable_coverage_stays_draft(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module
    _install_fake_ppo_training(monkeypatch, training_module)

    class EmptyFallbackProvider:
        name = "empty"

        def fetch_daily_bars(self, symbol: str, limit: int = 60):
            return []

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    monkeypatch.setattr(training_module, "FALLBACK_HISTORY_PROVIDERS", (EmptyFallbackProvider,))
    monkeypatch.setattr(training_module.BaoStockHistorySyncService, "sync_history", lambda self, **kwargs: None)
    _seed_daily_bars(db, "sh600519", days=36)
    symbols = ["sh600519"] + [f"sh6005{index:02d}" for index in range(20, 29)]

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "低覆盖训练模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": symbols,
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "limit": 20,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft"
    assert payload["metrics"]["candidate_symbol_count"] == 10
    assert payload["metrics"]["trainable_symbol_count"] == 1
    assert payload["metrics"]["trainable_symbol_ratio"] == 0.1
    assert payload["metrics"]["untrainable_symbol_count"] == 9
    assert payload["metrics"]["training_transition_count"] == payload["training"]["total_timesteps"]
    assert "trainable_symbols_too_few" in payload["validation"]["blockers"]
    assert "trainable_coverage_too_low" in payload["validation"]["blockers"]


def test_train_rl_model_uses_fallback_provider_when_baostock_login_fails(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module
    _install_fake_ppo_training(monkeypatch, training_module)

    class StubFallbackProvider:
        name = "eastmoney"

        def fetch_daily_bars(self, symbol: str, limit: int = 60):
            start = date(2025, 4, 1)
            return [_bar(symbol, start + timedelta(days=index), 10 + index * 0.1) for index in range(36)]

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    monkeypatch.setattr(training_module, "FALLBACK_HISTORY_PROVIDERS", (StubFallbackProvider,))

    def fake_sync(self, *, symbols, start_date, end_date, adjustflag="2", incremental=False, progress_callback=None):
        return BaoStockSyncResult(
            status="failed",
            source="baostock",
            adjustflag=adjustflag,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            requested_symbols=symbols,
            incremental=incremental,
            failures=[BaoStockSyncFailure(symbol=symbol, reason="baostock login failed: 网络接收错误。") for symbol in symbols],
            bars_upserted=0,
        )

    monkeypatch.setattr(training_module.BaoStockHistorySyncService, "sync_history", fake_sync)

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "备用数据源 RL 模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2025-04-01",
            "end_date": "2025-05-20",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["evaluated_symbol_count"] == 1
    assert payload["dataset_manifest"]["quality_summary"]["total_rows"] == 36


def test_train_rl_model_reports_baostock_sync_result_when_no_bars_upserted(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    class EmptyFallbackProvider:
        name = "eastmoney"

        def fetch_daily_bars(self, symbol: str, limit: int = 60):
            return []

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    monkeypatch.setattr(training_module, "FALLBACK_HISTORY_PROVIDERS", (EmptyFallbackProvider,))

    def fake_sync(self, *, symbols, start_date, end_date, adjustflag="2", incremental=False, progress_callback=None):
        return BaoStockSyncResult(
            status="failed",
            source="baostock",
            adjustflag=adjustflag,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            requested_symbols=symbols,
            incremental=incremental,
            failures=[BaoStockSyncFailure(symbol=symbols[0], reason="baostock history query failed: no data")],
            bars_upserted=0,
        )

    monkeypatch.setattr(training_module.BaoStockHistorySyncService, "sync_history", fake_sync)

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "同步无数据 RL 模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "limit": 5,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "baostock_sync=" in detail
    assert "'status': 'failed'" in detail
    assert "'bars_upserted': 0" in detail
    assert "baostock history query failed: no data" in detail
    assert "selected date range has only 51 calendar days" in detail


def test_train_rl_model_reports_daily_bar_counts_when_sync_still_insufficient(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    class EmptyFallbackProvider:
        name = "eastmoney"

        def fetch_daily_bars(self, symbol: str, limit: int = 60):
            return []

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    monkeypatch.setattr(training_module, "FALLBACK_HISTORY_PROVIDERS", (EmptyFallbackProvider,))
    monkeypatch.setattr(training_module.BaoStockHistorySyncService, "sync_history", lambda self, **kwargs: None)

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "缺数据 RL 模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "limit": 5,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "minimum=22" in detail
    assert "counts={'sh600519': 0}" in detail
    assert "widen the training date range" in detail


def test_train_rl_model_reports_insufficient_ppo_split(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module
    _install_fake_ppo_training(monkeypatch, training_module)

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    _seed_daily_bars(db, "sh600519", days=22)

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "切分不足 RL 模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-01-22",
            "min_validation_bars": 21,
            "limit": 5,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "no symbols have enough daily bars after train/validation split" in detail
    assert "min_validation_bars=21" in detail
    assert "resolved_symbol_count=1" in detail
    assert "dataset_count=22" in detail
    assert "trainable_symbol_count=1" in detail
    assert "split_train_symbol_count=0" in detail
    assert "split_validation_symbol_count=0" in detail
    assert "'sh600519': {'daily_bars': 22" in detail
    assert "'excluded_reason': 'validation_bars_too_few'" in detail
    assert "lower min_validation_bars" in detail


def test_rl_training_job_failure_keeps_ppo_split_snapshot(tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    def init_job_registry(self, root=None):
        self.root = tmp_path / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(training_module.RLTrainingJobRegistry, "__init__", init_job_registry)
    snapshot_details = [
        "no symbols have enough daily bars after train/validation split",
        "resolved_symbol_count=1",
        "dataset_count=22",
        "trainable_symbol_count=1",
        "split_train_symbol_count=0",
        "split_validation_symbol_count=0",
        "split_sample={'sh600519': {'daily_bars': 22, 'excluded_reason': 'validation_bars_too_few'}}",
    ]

    def fail_train(self, **kwargs):
        raise training_module.RLTrainingDataError(snapshot_details[0], progress_details=snapshot_details)

    monkeypatch.setattr(training_module.RLTrainingService, "train", fail_train)
    registry = training_module.RLTrainingJobRegistry()
    registry._write_status({"job_id": "job-failed", "status": "queued", "progress_details": []})
    registry._run_job("job-failed", {"model_name": "异步切分不足模型", "scope": "manual", "symbols": ["sh600519"]})

    latest = registry.get("job-failed")
    assert latest["status"] == "failed", latest
    details = latest["progress_details"]
    assert any("no symbols have enough daily bars after train/validation split" in item for item in details)
    assert "resolved_symbol_count=1" in details
    assert "dataset_count=22" in details
    assert "trainable_symbol_count=1" in details
    assert "split_train_symbol_count=0" in details
    assert "split_validation_symbol_count=0" in details
    assert any("'daily_bars': 22" in item and "validation_bars_too_few" in item for item in details)


def test_ppo_internal_split_error_includes_service_snapshot(db, client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    class FailingPPOTrainer:
        def __init__(self, config):
            self.config = config

        def train(self, records_by_symbol, *, model_path, progress_callback=None, dataset_split=None):
            raise ValueError("no symbols have enough daily bars after train/validation split; please widen the training date range or lower min_validation_bars")

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    monkeypatch.setattr(training_module, "PPOTradingTrainer", FailingPPOTrainer)
    _seed_daily_bars(db, "sh600519", days=45)

    response = client.post(
        "/api/v1/market/rl/training/train",
        json={
            "model_name": "PPO 内部失败快照模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
            "total_timesteps": 1000,
            "limit": 5,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "no symbols have enough daily bars after train/validation split" in detail
    assert "resolved_symbol_count=1" in detail
    assert "dataset_count=45" in detail
    assert "trainable_symbol_count=1" in detail
    assert "split_train_symbol_count=1" in detail
    assert "split_validation_symbol_count=1" in detail
    assert "'daily_bars': 45" in detail
    assert "'included_in_training': True" in detail


def test_ppo_evaluation_skips_prediction_for_single_bar_prefix(monkeypatch) -> None:
    import app.quant.training as training_module
    from app.quant.ppo_training import PPOTrainingConfig
    from app.quant.simulator import RLEpisodeConfig

    calls: list[int] = []

    def fake_predict(artifact, records, model=None):
        calls.append(len(records))
        if len(records) < 2:
            raise AssertionError("single-bar prefixes must not call PPO prediction")
        return {"action_index": 4, "action_type": "buy", "target_position_pct": 1.0}

    monkeypatch.setattr(training_module, "predict_ppo_action", fake_predict)
    records = [
        {
            "symbol": "sz300063",
            "trade_date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "open_price": 10 + index,
            "close_price": 10 + index,
            "high_price": 10 + index,
            "low_price": 10 + index,
            "volume": 1000000,
            "turnover": 10000000,
            "trade_status": 1,
        }
        for index in range(3)
    ]

    evaluations = training_module.RLTrainingService(None)._evaluate_ppo_policy(
        {"sz300063": records},
        policy_model=object(),
        ppo_config=PPOTrainingConfig(),
        episode_config=RLEpisodeConfig(commission_rate=0.0, slippage_rate=0.0),
    )

    assert calls == [2, 3]
    assert evaluations[0]["records"] == 3


def test_rl_strategy_falls_back_for_legacy_q_learning_model(tmp_path, monkeypatch) -> None:
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

    assert signal["trigger_reason"] == "rl_trained_model_unsupported_algorithm"
    assert signal["rl_action"]["policy_mode"] == "trained_model"
    assert signal["signal"] == "hold"


def test_latest_rl_training_job_returns_most_recent_job(client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    def init_job_registry(self, root=None):
        self.root = tmp_path / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(training_module.RLTrainingJobRegistry, "__init__", init_job_registry)

    registry = training_module.RLTrainingJobRegistry()
    old_job = {
        "job_id": "job-old",
        "status": "succeeded",
        "progress_step": 1,
        "progress_total": 1,
        "progress_pct": 100.0,
        "progress_label": "训练完成",
        "progress_details": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "started_at": None,
        "finished_at": "2026-01-01T00:00:00Z",
        "model_id": "old-model",
        "model": None,
        "error": None,
    }
    new_job = {**old_job, "job_id": "job-new", "updated_at": "2026-01-02T00:00:00Z", "model_id": "new-model"}
    registry._write_status(old_job)
    registry._write_status(new_job)

    response = client.get("/api/v1/market/rl/training/jobs/latest")

    assert response.status_code == 200
    assert response.json()["job_id"] == "job-new"


def test_rl_training_job_status_write_is_atomic(tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    def init_job_registry(self, root=None):
        self.root = tmp_path / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(training_module.RLTrainingJobRegistry, "__init__", init_job_registry)
    registry = training_module.RLTrainingJobRegistry()

    registry._write_status({
        "job_id": "job-atomic",
        "status": "queued",
        "progress_step": 0,
        "progress_total": 1,
        "progress_pct": 0.0,
        "progress_label": "排队中",
        "progress_details": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "started_at": None,
        "finished_at": None,
        "model_id": None,
        "model": None,
        "error": None,
    })

    assert registry.get("job-atomic")["status"] == "queued"
    assert not list((tmp_path / "jobs").glob("*.tmp"))


def test_rl_training_job_normalizes_legacy_ppo_daily_bar_error(tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    def init_job_registry(self, root=None):
        self.root = tmp_path / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(training_module.RLTrainingJobRegistry, "__init__", init_job_registry)
    registry = training_module.RLTrainingJobRegistry()
    registry._write_status({
        "job_id": "job-legacy-error",
        "status": "failed",
        "progress_step": 6,
        "progress_total": 8,
        "progress_pct": 100.0,
        "progress_label": "训练失败",
        "progress_details": ["PPO training requires at least one symbol with two daily bars"],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "model_id": None,
        "model": None,
        "error": "PPO training requires at least one symbol with two daily bars",
    })

    payload = registry.get("job-legacy-error")

    assert payload is not None
    assert "two daily bars" not in str(payload["error"])
    assert "two daily bars" not in str(payload["progress_details"])
    assert "widen the training date range" in str(payload["error"])


def test_rl_training_job_reports_progress_and_result(client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    def init_job_registry(self, root=None):
        self.root = tmp_path / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(training_module.RLTrainingJobRegistry, "__init__", init_job_registry)

    def fake_train(self, **kwargs):
        progress = kwargs.get("progress_callback")
        if progress:
            progress(1, 2, "fake half", ["解析范围"])
            progress(2, 2, "fake done", ["保存模型"])
        return {
            "model_id": "job-model",
            "name": kwargs["model_name"],
            "status": "validated",
            "algorithm": "ppo_trading",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "scope": kwargs["scope"],
            "symbols": [],
            "config": {},
            "training": {},
            "metrics": {"trade_count": 1},
            "validation": {"passed": True, "blockers": [], "warnings": []},
            "evaluations": [],
            "dataset_manifest": {},
        }

    monkeypatch.setattr(training_module.RLTrainingService, "train", fake_train)

    submit = client.post(
        "/api/v1/market/rl/training/jobs",
        json={
            "model_name": "异步测试模型",
            "algorithm": "ppo_trading",
            "scope": "manual",
            "symbols": ["sh600519"],
            "start_date": "2026-01-01",
            "end_date": "2026-02-20",
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
    assert latest["progress_details"] == ["模型产物已保存", "模型列表已刷新"]
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


def test_delete_rl_model_removes_registry_artifacts(client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))
    registry = training_module.RLModelRegistry()
    registry.save({
        "model_id": "delete-model",
        "name": "待删除模型",
        "status": "validated",
        "algorithm": "ppo_trading",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "scope": "manual",
        "symbols": [],
        "config": {},
        "training": {},
        "metrics": {"trade_count": 0},
        "validation": {"passed": True, "blockers": []},
        "evaluations": [],
        "dataset_manifest": {},
    })
    (tmp_path / "delete-model" / "policy.zip").write_bytes(b"policy")

    response = client.delete("/api/v1/market/rl/models/delete-model")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "model_id": "delete-model"}
    assert not (tmp_path / "delete-model").exists()
    assert client.get("/api/v1/market/rl/models/delete-model").status_code == 404


def test_delete_missing_rl_model_returns_not_found(client, tmp_path, monkeypatch) -> None:
    import app.quant.training as training_module

    monkeypatch.setattr(training_module.RLModelRegistry, "__init__", lambda self, root=None: setattr(self, "root", tmp_path))

    response = client.delete("/api/v1/market/rl/models/missing-model")

    assert response.status_code == 404
    assert response.json()["detail"] == "rl model not found"


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


def test_resolve_rl_training_symbols_merges_multiple_scopes(db, client) -> None:
    db.add(WatchlistItem(symbol="sh600519", is_special_attention=True, is_pinned=True, sort_order=0))
    db.add(WatchlistItem(symbol="sz000001", is_special_attention=False, is_pinned=False, sort_order=1))
    db.commit()

    response = client.post(
        "/api/v1/market/rl/training/resolve",
        json={"scope": "watchlist", "scopes": ["special_attention", "manual"], "symbols": ["sz300750"], "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "special_attention+manual"
    assert [item["symbol"] for item in payload["symbols"]] == ["sh600519", "sz300750"]


def test_resolve_rl_training_symbols_defaults_null_limit(db, client) -> None:
    db.add(WatchlistItem(symbol="sh600519"))
    db.commit()

    response = client.post("/api/v1/market/rl/training/resolve", json={"scope": "watchlist", "limit": None})

    assert response.status_code == 200
    assert response.json()["symbols"][0]["symbol"] == "sh600519"
