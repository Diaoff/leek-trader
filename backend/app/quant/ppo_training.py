from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

import numpy as np

from app.quant.simulator import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_DRAWDOWN_ACTIVE_POSITION_REWARD,
    DEFAULT_DRAWDOWN_PENALTY_COEF,
    DEFAULT_INITIAL_CASH,
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_REWARD_MODE,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TURNOVER_PENALTY_COEF,
    RLRewardMode,
)

try:  # optional heavy dependency
    import gymnasium as gym
    from gymnasium import spaces
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
except ImportError:  # pragma: no cover - exercised via dependency-missing paths
    gym = None
    spaces = None
    PPO = None
    BaseCallback = object  # type: ignore[assignment]

PPO_ALGORITHM = "ppo_trading"
PPO_ACTION_SPACE = [0.0, 0.25, 0.5, 0.75, 1.0]
PPO_OBSERVATION_VERSION = "ppo-observation/v2"
PPO_OBSERVATION_FEATURES = [
    "return_since_start",
    "return_1d",
    "return_3d",
    "return_5d",
    "return_10d",
    "return_20d",
    "open_to_close",
    "high_to_close",
    "low_to_close",
    "amplitude_pct",
    "change_pct",
    "volume_ratio_20d",
    "turnover_ratio_20d",
    "turnover_rate",
    "ma5_deviation",
    "ma10_deviation",
    "ma20_deviation",
    "ma5_ma20_spread",
    "volatility_20d",
    "max_drawdown_20d",
    "cash_ratio",
    "position_pct",
    "unrealized_pnl",
    "account_drawdown",
    "progress_pct",
    "pe_ttm",
    "pb_mrq",
    "trade_status",
]
PPO_OBSERVATION_SIZE = len(PPO_OBSERVATION_FEATURES)


@dataclass(slots=True)
class PPOTrainingConfig:
    total_timesteps: int = 100_000
    train_split_pct: float = 0.8
    n_steps: int = 512
    batch_size: int = 64
    learning_rate: float = 0.00031
    initial_cash: float = DEFAULT_INITIAL_CASH
    commission_rate: float = DEFAULT_COMMISSION_RATE
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE
    reward_mode: RLRewardMode = DEFAULT_REWARD_MODE
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT
    drawdown_penalty_coef: float = DEFAULT_DRAWDOWN_PENALTY_COEF
    turnover_penalty_coef: float = DEFAULT_TURNOVER_PENALTY_COEF
    min_validation_bars: int = 5


@dataclass(slots=True)
class PPODatasetSplit:
    train: dict[str, list[dict[str, Any]]]
    validation: dict[str, list[dict[str, Any]]]
    metadata: dict[str, dict[str, Any]]


class MultiStockTradingEnv(gym.Env if gym is not None else object):  # type: ignore[misc]
    metadata = {"render_modes": []}

    def __init__(self, records_by_symbol: dict[str, list[dict[str, Any]]], config: PPOTrainingConfig) -> None:
        if gym is None or spaces is None:
            raise RuntimeError("stable-baselines3/gymnasium is not installed; install backend requirements to train PPO models")
        self.records_by_symbol = {
            symbol: sorted(records, key=lambda item: str(item["trade_date"]))
            for symbol, records in records_by_symbol.items()
            if len(records) >= 2
        }
        if not self.records_by_symbol:
            raise ValueError("no symbols have enough daily bars after train/validation split; please widen the training date range or lower min_validation_bars")
        self.symbols = sorted(self.records_by_symbol)
        self.config = config
        self.action_space = spaces.Discrete(len(PPO_ACTION_SPACE))
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(PPO_OBSERVATION_SIZE,), dtype=np.float32)
        self._episode_cursor = 0
        self.current_symbol = self.symbols[0]
        self.records = self.records_by_symbol[self.current_symbol]
        self.current_step = 0
        self.cash = config.initial_cash
        self.shares = 0
        self.cost_basis = 0.0
        self.peak_net_worth = config.initial_cash
        self.previous_net_worth = config.initial_cash
        self.previous_close = float(self.records[0]["close_price"])
        self.last_reward_breakdown = self._empty_reward_breakdown()

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        if options and options.get("symbol") in self.records_by_symbol:
            self.current_symbol = str(options["symbol"])
        else:
            self.current_symbol = self.symbols[self._episode_cursor % len(self.symbols)]
            self._episode_cursor += 1
        self.records = self.records_by_symbol[self.current_symbol]
        self.current_step = 0
        self.cash = self.config.initial_cash
        self.shares = 0
        self.cost_basis = 0.0
        self.peak_net_worth = self.config.initial_cash
        self.previous_net_worth = self.config.initial_cash
        self.previous_close = self._close(0)
        self.last_reward_breakdown = self._empty_reward_breakdown()
        return self._observation(), {"symbol": self.current_symbol}

    def step(self, action: int):
        action_index = int(action)
        target_pct = min(PPO_ACTION_SPACE[max(0, min(action_index, len(PPO_ACTION_SPACE) - 1))], self.config.max_position_pct)
        close_price = self._close(self.current_step)
        traded_value, fee = self._rebalance(close_price, target_pct)
        position_value = self.shares * close_price
        net_worth = self.cash + position_value
        self.peak_net_worth = max(self.peak_net_worth, net_worth)
        drawdown_pct = 0.0 if self.peak_net_worth <= 0 else (self.peak_net_worth - net_worth) / self.peak_net_worth * 100
        benchmark_return = 0.0 if self.previous_close <= 0 else (close_price - self.previous_close) / self.previous_close
        portfolio_return = 0.0 if self.previous_net_worth <= 0 else (net_worth - self.previous_net_worth) / self.previous_net_worth
        turnover_pct = 0.0 if self.previous_net_worth <= 0 else traded_value / self.previous_net_worth
        cost_pct = 0.0 if self.previous_net_worth <= 0 else fee / self.previous_net_worth
        position_pct = 0.0 if net_worth <= 0 else position_value / net_worth
        reward = self._reward(
            portfolio_return=portfolio_return,
            benchmark_return=benchmark_return,
            drawdown_pct=drawdown_pct,
            turnover_pct=turnover_pct,
            cost_pct=cost_pct,
            position_pct=position_pct,
        )
        self.previous_net_worth = net_worth
        self.previous_close = close_price
        self.current_step += 1
        terminated = net_worth <= 0
        truncated = self.current_step >= len(self.records) - 1
        return self._observation(), float(reward), terminated, truncated, {"symbol": self.current_symbol, "net_worth": net_worth, "reward_breakdown": self.last_reward_breakdown}

    def action_for_observation(self, observation: np.ndarray, model: Any) -> dict[str, Any]:
        action, _states = model.predict(observation.reshape(1, -1), deterministic=True)
        action_index = int(np.asarray(action).reshape(-1)[0])
        target_pct = PPO_ACTION_SPACE[max(0, min(action_index, len(PPO_ACTION_SPACE) - 1))]
        action_type = "buy" if target_pct >= 0.5 else "sell" if target_pct <= 0 else "hold"
        return {"action_index": action_index, "action_type": action_type, "target_position_pct": target_pct}

    def _reward(
        self,
        *,
        portfolio_return: float,
        benchmark_return: float,
        drawdown_pct: float,
        turnover_pct: float = 0.0,
        cost_pct: float = 0.0,
        position_pct: float = 0.0,
    ) -> float:
        excess_return = portfolio_return - benchmark_return
        drawdown_penalty = max(0.0, drawdown_pct) * 0.01 * self.config.drawdown_penalty_coef
        turnover_penalty = max(0.0, turnover_pct) * self.config.turnover_penalty_coef + max(0.0, cost_pct)
        active_position_reward = max(0.0, min(position_pct, 1.0)) * DEFAULT_DRAWDOWN_ACTIVE_POSITION_REWARD
        if self.config.reward_mode == "risk_adjusted_excess_return":
            reward = excess_return - drawdown_penalty - turnover_penalty
            self.last_reward_breakdown = {
                "return_term": round(portfolio_return, 10),
                "benchmark_term": round(benchmark_return, 10),
                "excess_return": round(excess_return, 10),
                "drawdown_penalty": round(drawdown_penalty, 10),
                "turnover_penalty": round(turnover_penalty, 10),
                "reward": round(reward, 10),
            }
            return reward
        if self.config.reward_mode == "excess_return":
            reward = excess_return
            self.last_reward_breakdown = self._legacy_reward_breakdown(portfolio_return, benchmark_return, drawdown_penalty, turnover_penalty, reward)
            return reward
        if self.config.reward_mode == "drawdown_penalty":
            reward = portfolio_return - drawdown_penalty + active_position_reward
            self.last_reward_breakdown = self._legacy_reward_breakdown(
                portfolio_return,
                benchmark_return,
                drawdown_penalty,
                turnover_penalty,
                reward,
                active_position_reward=active_position_reward,
            )
            return reward
        reward = portfolio_return
        self.last_reward_breakdown = self._legacy_reward_breakdown(portfolio_return, benchmark_return, drawdown_penalty, turnover_penalty, reward)
        return reward

    def _rebalance(self, price: float, target_pct: float) -> tuple[float, float]:
        if price <= 0:
            return 0.0, 0.0
        net_worth = self.cash + self.shares * price
        target_value = net_worth * target_pct
        current_value = self.shares * price
        delta_value = target_value - current_value
        execution_price = price * (1 + self.config.slippage_rate if delta_value > 0 else 1 - self.config.slippage_rate)
        if delta_value > 0:
            affordable = self.cash / (execution_price * (1 + self.config.commission_rate))
            shares_delta = max(0, int(min(delta_value / execution_price, affordable)))
            cost = shares_delta * execution_price
            fee = cost * self.config.commission_rate
            if shares_delta > 0:
                self.cost_basis = ((self.cost_basis * self.shares) + cost) / (self.shares + shares_delta)
                self.shares += shares_delta
                self.cash -= cost + fee
                return cost, fee
        elif delta_value < 0:
            shares_delta = max(0, min(self.shares, int(abs(delta_value) / execution_price)))
            proceeds = shares_delta * execution_price
            fee = proceeds * self.config.commission_rate
            self.shares -= shares_delta
            self.cash += proceeds - fee
            if self.shares <= 0:
                self.cost_basis = 0.0
            return proceeds, fee
        return 0.0, 0.0

    def _observation(self) -> np.ndarray:
        index = max(0, min(self.current_step, len(self.records) - 1))
        record = self.records[index]
        close = self._close(index)
        prev_close = self._close(max(0, index - 1))
        first_close = self._close(0)
        ma5 = self._moving_average(index, 5)
        ma10 = self._moving_average(index, 10)
        ma20 = self._moving_average(index, 20)
        returns = [self._close(i) / self._close(i - 1) - 1 for i in range(max(1, index - 19), index + 1) if self._close(i - 1) > 0]
        volatility = float(np.std(returns)) if returns else 0.0
        volume = float(record.get("volume") or 0)
        volumes = [float(item.get("volume") or 0) for item in self.records[max(0, index - 19): index + 1]]
        avg_volume = sum(volumes) / len(volumes) if volumes else volume
        turnover = self._liquidity_value(record, "turnover", close * volume)
        turnovers = [self._liquidity_value(item, "turnover", self._close(row_index) * float(item.get("volume") or 0)) for row_index, item in enumerate(self.records[max(0, index - 19): index + 1], start=max(0, index - 19))]
        avg_turnover = sum(turnovers) / len(turnovers) if turnovers else turnover
        position_value = self.shares * close
        net_worth = self.cash + position_value
        unrealized = 0.0 if self.cost_basis <= 0 else close / self.cost_basis - 1
        drawdown = 0.0 if self.peak_net_worth <= 0 else (self.peak_net_worth - net_worth) / self.peak_net_worth
        obs = np.array([self._feature_value(feature, index, record, close, prev_close, first_close, ma5, ma10, ma20, volatility, volume, avg_volume, turnover, avg_turnover, net_worth, position_value, unrealized, drawdown) for feature in PPO_OBSERVATION_FEATURES], dtype=np.float32)
        return np.nan_to_num(obs, nan=0.0, posinf=10.0, neginf=-10.0).clip(-10.0, 10.0)

    def _feature_value(self, feature: str, index: int, record: dict[str, Any], close: float, prev_close: float, first_close: float, ma5: float, ma10: float, ma20: float, volatility: float, volume: float, avg_volume: float, turnover: float, avg_turnover: float, net_worth: float, position_value: float, unrealized: float, drawdown: float) -> float:
        if feature.startswith("return_") and feature.endswith("d"):
            window = int(feature.removeprefix("return_").removesuffix("d"))
            return self._window_return(index, window)
        if feature == "return_since_start":
            return self._safe_ratio(close, first_close) - 1
        if feature == "open_to_close":
            return self._safe_ratio(float(record.get("open_price") or close), close) - 1
        if feature == "high_to_close":
            return self._safe_ratio(float(record.get("high_price") or close), close) - 1
        if feature == "low_to_close":
            return self._safe_ratio(float(record.get("low_price") or close), close) - 1
        if feature == "amplitude_pct":
            fallback = (float(record.get("high_price") or close) - float(record.get("low_price") or close)) / close * 100 if close > 0 else 0.0
            return float(record.get("amplitude_pct") if record.get("amplitude_pct") is not None else fallback) / 100
        if feature == "change_pct":
            fallback = (self._safe_ratio(close, prev_close) - 1) * 100
            return float(record.get("change_pct") if record.get("change_pct") is not None else fallback) / 100
        if feature == "volume_ratio_20d":
            return self._safe_ratio(volume, avg_volume) - 1
        if feature == "turnover_ratio_20d":
            return self._safe_ratio(turnover, avg_turnover) - 1
        if feature == "turnover_rate":
            return float(record.get("turnover_rate") or 0) / 100
        if feature == "ma5_deviation":
            return self._safe_ratio(close, ma5) - 1
        if feature == "ma10_deviation":
            return self._safe_ratio(close, ma10) - 1
        if feature == "ma20_deviation":
            return self._safe_ratio(close, ma20) - 1
        if feature == "ma5_ma20_spread":
            return self._safe_ratio(ma5, ma20) - 1
        if feature == "volatility_20d":
            return volatility
        if feature == "max_drawdown_20d":
            return self._rolling_max_drawdown(index, 20)
        if feature == "cash_ratio":
            return self.cash / max(net_worth, 1.0)
        if feature == "position_pct":
            return position_value / max(net_worth, 1.0)
        if feature == "unrealized_pnl":
            return unrealized
        if feature == "account_drawdown":
            return drawdown
        if feature == "progress_pct":
            return index / max(len(self.records) - 1, 1)
        if feature == "pe_ttm":
            return float(record.get("pe_ttm") or 0) / 100
        if feature == "pb_mrq":
            return float(record.get("pb_mrq") or 0) / 20
        if feature == "trade_status":
            return float(record.get("trade_status") if record.get("trade_status") is not None else 1)
        return 0.0

    def _close(self, index: int) -> float:
        return float(self.records[index].get("close_price") or 0)

    def _moving_average(self, index: int, window: int) -> float:
        start = max(0, index + 1 - window)
        closes = [self._close(i) for i in range(start, index + 1)]
        return sum(closes) / len(closes) if closes else self._close(index)

    def _window_return(self, index: int, window: int) -> float:
        base_index = max(0, index - window)
        base = self._close(base_index)
        return self._safe_ratio(self._close(index), base) - 1

    def _rolling_max_drawdown(self, index: int, window: int) -> float:
        start = max(0, index + 1 - window)
        closes = [self._close(i) for i in range(start, index + 1)]
        peak = closes[0] if closes else 0.0
        max_drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - close) / peak)
        return max_drawdown

    @staticmethod
    def _liquidity_value(record: dict[str, Any], field: str, fallback: float) -> float:
        value = record.get(field)
        return float(value) if value is not None else fallback

    @staticmethod
    def _empty_reward_breakdown() -> dict[str, float]:
        return {
            "return_term": 0.0,
            "benchmark_term": 0.0,
            "excess_return": 0.0,
            "drawdown_penalty": 0.0,
            "turnover_penalty": 0.0,
            "active_position_reward": 0.0,
            "reward": 0.0,
        }

    @staticmethod
    def _legacy_reward_breakdown(
        portfolio_return: float,
        benchmark_return: float,
        drawdown_penalty: float,
        turnover_penalty: float,
        reward: float,
        *,
        active_position_reward: float = 0.0,
    ) -> dict[str, float]:
        return {
            "return_term": round(portfolio_return, 10),
            "benchmark_term": round(benchmark_return, 10),
            "excess_return": round(portfolio_return - benchmark_return, 10),
            "drawdown_penalty": round(drawdown_penalty, 10),
            "turnover_penalty": round(turnover_penalty, 10),
            "active_position_reward": round(active_position_reward, 10),
            "reward": round(reward, 10),
        }

    @staticmethod
    def _safe_ratio(value: float, base: float) -> float:
        return 0.0 if base == 0 else value / base


class PPOProgressCallback(BaseCallback if PPO is not None else object):  # type: ignore[misc]
    def __init__(self, total_timesteps: int, progress_callback: Callable[[int, int, str, list[str] | None], None] | None = None) -> None:
        if PPO is not None:
            super().__init__()
        self.total_timesteps = max(total_timesteps, 1)
        self.progress_callback = progress_callback
        self._last_bucket = -1

    def _on_step(self) -> bool:
        if self.progress_callback is None:
            return True
        bucket = int((self.num_timesteps / self.total_timesteps) * 20)
        if bucket != self._last_bucket:
            self._last_bucket = bucket
            self.progress_callback(
                min(self.num_timesteps, self.total_timesteps),
                self.total_timesteps,
                f"PPO 训练步数 {min(self.num_timesteps, self.total_timesteps)}/{self.total_timesteps}",
                [f"完成度：{min(100.0, self.num_timesteps / self.total_timesteps * 100):.1f}%"],
            )
        return True


class PPOTradingTrainer:
    def __init__(self, config: PPOTrainingConfig) -> None:
        if PPO is None or gym is None:
            raise RuntimeError("stable-baselines3/gymnasium is not installed; install backend requirements to train PPO models")
        self.config = config

    def train(
        self,
        records_by_symbol: dict[str, list[dict[str, Any]]],
        *,
        model_path: Path,
        progress_callback: Callable[[int, int, str, list[str] | None], None] | None = None,
        dataset_split: PPODatasetSplit | None = None,
    ) -> dict[str, Any]:
        split = dataset_split or split_records_by_symbol(records_by_symbol, self.config.train_split_pct, min_validation_bars=self.config.min_validation_bars)
        train_records = split.train
        validation_records = split.validation
        env = MultiStockTradingEnv(train_records, self.config)
        model = PPO(
            "MlpPolicy",
            env,
            verbose=0,
            n_steps=self.config.n_steps,
            batch_size=self.config.batch_size,
            learning_rate=self.config.learning_rate,
        )
        model.learn(total_timesteps=self.config.total_timesteps, callback=PPOProgressCallback(self.config.total_timesteps, progress_callback))
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(str(model_path))
        return {
            "algorithm": PPO_ALGORITHM,
            "policy_path": model_path.name,
            "observation_size": PPO_OBSERVATION_SIZE,
            "observation_version": PPO_OBSERVATION_VERSION,
            "observation_features": list(PPO_OBSERVATION_FEATURES),
            "action_space": PPO_ACTION_SPACE,
            "total_timesteps": self.config.total_timesteps,
            "train_symbol_count": len(train_records),
            "validation_symbol_count": len(validation_records),
            "splits": split.metadata,
            "hyperparameters": {
                "train_split_pct": self.config.train_split_pct,
                "n_steps": self.config.n_steps,
                "batch_size": self.config.batch_size,
                "learning_rate": self.config.learning_rate,
                "reward_mode": self.config.reward_mode,
                "drawdown_penalty_coef": self.config.drawdown_penalty_coef,
                "turnover_penalty_coef": self.config.turnover_penalty_coef,
                "min_validation_bars": self.config.min_validation_bars,
            },
        }


def split_records_by_symbol(records_by_symbol: dict[str, list[dict[str, Any]]], train_split_pct: float, *, min_validation_bars: int = 5) -> PPODatasetSplit:
    train: dict[str, list[dict[str, Any]]] = {}
    validation: dict[str, list[dict[str, Any]]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    split_pct = min(max(train_split_pct, 0.5), 0.95)
    min_validation_bars = max(1, int(min_validation_bars or 1))
    for symbol, records in records_by_symbol.items():
        ordered = sorted(records, key=lambda item: str(item["trade_date"]))
        if len(ordered) < 3:
            metadata[symbol] = {
                "included_in_training": False,
                "excluded_reason": "too_few_bars",
                "total_bars": len(ordered),
                "train_bars": 0,
                "validation_bars": 0,
            }
            continue
        split_index = max(2, min(len(ordered) - min_validation_bars, int(len(ordered) * split_pct)))
        if split_index < 2 or len(ordered) - split_index < min_validation_bars:
            metadata[symbol] = {
                "included_in_training": False,
                "excluded_reason": "validation_bars_too_few",
                "total_bars": len(ordered),
                "train_bars": 0,
                "validation_bars": 0,
                "min_validation_bars": min_validation_bars,
            }
            continue
        train[symbol] = ordered[:split_index]
        validation[symbol] = ordered[split_index:]
        metadata[symbol] = {
            "included_in_training": True,
            "excluded_reason": None,
            "total_bars": len(ordered),
            "train_bars": len(train[symbol]),
            "validation_bars": len(validation[symbol]),
            "train_start_date": str(train[symbol][0]["trade_date"]),
            "train_end_date": str(train[symbol][-1]["trade_date"]),
            "validation_start_date": str(validation[symbol][0]["trade_date"]),
            "validation_end_date": str(validation[symbol][-1]["trade_date"]),
            "min_validation_bars": min_validation_bars,
        }
    return PPODatasetSplit(train=train, validation=validation, metadata=metadata)


def load_ppo_model(model_path: Path) -> Any:
    if PPO is None:
        raise RuntimeError("stable-baselines3/gymnasium is not installed; install backend requirements to use PPO models")
    return PPO.load(str(model_path))


def predict_ppo_action(artifact: dict[str, Any], records: list[dict[str, Any]], *, registry_root: Path | None = None, model: Any | None = None) -> dict[str, Any]:
    model_id = str(artifact.get("model_id") or "")
    policy_path = str(artifact.get("training", {}).get("policy_path") or "policy.zip")
    root = registry_root or Path(__file__).resolve().parents[3] / "artifacts" / "rl_models"
    full_path = root / model_id / policy_path
    model = model or load_ppo_model(full_path)
    config_payload = artifact.get("config", {}) or {}
    config = PPOTrainingConfig(
        initial_cash=float(config_payload.get("initial_cash") or 100_000.0),
        commission_rate=float(config_payload.get("commission_rate") or 0.0003),
        slippage_rate=float(config_payload.get("slippage_rate") or 0.0002),
        reward_mode=str(config_payload.get("reward_mode") or "net_worth_change"),  # type: ignore[arg-type]
        max_position_pct=float(config_payload.get("max_position_pct") or 1.0),
    )
    env = MultiStockTradingEnv({"predict": records}, config)
    observation, _info = env.reset(options={"symbol": "predict"})
    env.current_step = len(env.records) - 1
    observation = env._observation()
    return env.action_for_observation(observation, model)
