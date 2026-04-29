from __future__ import annotations

import json
import math
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.market.rl_dataset_service import RLDatasetBuilder
from app.market.security_names import security_name
from app.market.symbols import normalize_a_share_symbol
from app.models.smart_selection_item import SmartSelectionItem
from app.models.smart_selection_institution_pool_item import SmartSelectionInstitutionPoolItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus
from app.models.watchlist import WatchlistItem
from app.quant.simulator import RLEpisodeConfig, RLEpisodeSimulator

RLTrainingScope = Literal["watchlist", "special_attention", "smart_selection", "manual"]
RLModelStatus = Literal["draft", "validated", "active", "retired"]
RLTrainingJobStatus = Literal["queued", "running", "succeeded", "failed"]

POSITION_ACTIONS = [0.0, 0.25, 0.5, 0.75, 1.0]


@dataclass(slots=True)
class RLTrainingSymbol:
    symbol: str
    name: str | None = None
    source: str = "manual"


class RLModelRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[3] / "artifacts" / "rl_models"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, artifact: dict[str, Any]) -> dict[str, Any]:
        model_id = str(artifact["model_id"])
        model_dir = self.root / model_id
        model_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(model_dir / "model.json", artifact)
        self._write_json(model_dir / "metrics.json", artifact.get("metrics", {}))
        self._write_json(model_dir / "config.json", artifact.get("config", {}))
        return artifact

    def list_models(self) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        for model_path in sorted(self.root.glob("*/model.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                models.append(json.loads(model_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return models

    def load(self, model_id: str) -> dict[str, Any] | None:
        path = self.root / model_id / "model.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def update_status(self, model_id: str, status: RLModelStatus) -> dict[str, Any] | None:
        artifact = self.load(model_id)
        if artifact is None:
            return None
        artifact["status"] = status
        artifact["updated_at"] = datetime.now(UTC).isoformat()
        return self.save(artifact)

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


class TabularRLPolicy:
    def __init__(self, q_table: dict[str, list[float]], *, default_action_index: int = 0) -> None:
        self.q_table = q_table
        self.default_action_index = default_action_index

    def action_index_for_state(self, state_key: str) -> int:
        values = self.q_table.get(state_key)
        if not values:
            return self.default_action_index
        return max(range(len(values)), key=lambda index: values[index])

    def action_for_record(self, records: list[dict[str, Any]], index: int) -> dict[str, Any]:
        state_key = state_key_for_records(records, index)
        action_index = self.action_index_for_state(state_key)
        target_position_pct = POSITION_ACTIONS[action_index]
        action_type = "hold"
        if target_position_pct >= 0.5:
            action_type = "buy"
        elif target_position_pct == 0.0:
            action_type = "sell"
        return {
            "trade_date": str(records[index]["trade_date"]),
            "action": {
                "action_type": action_type,
                "target_position_pct": target_position_pct,
            },
            "state_key": state_key,
        }

def symbol_to_dict(item: RLTrainingSymbol) -> dict[str, Any]:
    return {"symbol": item.symbol, "name": item.name, "source": item.source}


def state_key_for_records(records: list[dict[str, Any]], index: int) -> str:
    current = records[index]
    close = _as_float(current.get("close_price"))
    previous_close = _as_float(records[index - 1].get("close_price")) if index > 0 else close
    change_pct = 0.0 if previous_close <= 0 else (close / previous_close - 1) * 100
    ma5 = _moving_average(records, index, 5)
    ma20 = _moving_average(records, index, 20)
    volume_ratio = _volume_ratio(records, index, 20)
    volatility20 = _volatility(records, index, 20)

    trend_bucket = "unknown"
    if ma5 and ma20:
        if ma5 > ma20 * 1.01:
            trend_bucket = "up"
        elif ma5 < ma20 * 0.99:
            trend_bucket = "down"
        else:
            trend_bucket = "flat"

    momentum_bucket = "flat"
    if change_pct >= 2:
        momentum_bucket = "strong_up"
    elif change_pct >= 0.5:
        momentum_bucket = "up"
    elif change_pct <= -2:
        momentum_bucket = "strong_down"
    elif change_pct <= -0.5:
        momentum_bucket = "down"

    volume_bucket = "normal"
    if volume_ratio >= 1.5:
        volume_bucket = "high"
    elif volume_ratio <= 0.75:
        volume_bucket = "low"

    volatility_bucket = "normal"
    if volatility20 >= 0.08:
        volatility_bucket = "high"
    elif volatility20 <= 0.03:
        volatility_bucket = "low"

    return "|".join([trend_bucket, momentum_bucket, volume_bucket, volatility_bucket])


class TabularQLearningTrainer:
    def __init__(
        self,
        *,
        learning_rate: float = 0.2,
        discount_factor: float = 0.9,
        exploration_rate: float = 0.1,
        episodes: int = 25,
    ) -> None:
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.exploration_rate = exploration_rate
        self.episodes = max(1, episodes)

    def train(
        self,
        records_by_symbol: dict[str, list[dict[str, Any]]],
        *,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        q_values: dict[str, list[float]] = defaultdict(lambda: [0.0 for _ in POSITION_ACTIONS])
        transitions = 0
        for episode in range(self.episodes):
            if progress_callback is not None:
                progress_callback(episode + 1, self.episodes, f"训练轮次 {episode + 1}/{self.episodes}")
            for records in records_by_symbol.values():
                if len(records) < 22:
                    continue
                for index in range(20, len(records) - 1):
                    state = state_key_for_records(records, index)
                    action_index = self._choose_action(q_values[state], episode=episode, state=state)
                    reward = self._reward(records, index, POSITION_ACTIONS[action_index])
                    next_state = state_key_for_records(records, index + 1)
                    best_next = max(q_values[next_state])
                    q_values[state][action_index] += self.learning_rate * (
                        reward + self.discount_factor * best_next - q_values[state][action_index]
                    )
                    transitions += 1

        serializable = {key: [round(value, 10) for value in values] for key, values in q_values.items()}
        return {
            "algorithm": "tabular_q_learning",
            "action_space": POSITION_ACTIONS,
            "q_table": serializable,
            "state_count": len(serializable),
            "transitions": transitions,
            "episodes": self.episodes,
            "hyperparameters": {
                "learning_rate": self.learning_rate,
                "discount_factor": self.discount_factor,
                "exploration_rate": self.exploration_rate,
            },
        }

    def _choose_action(self, values: list[float], *, episode: int, state: str) -> int:
        deterministic_noise = abs(hash((state, episode))) % 10000 / 10000
        if deterministic_noise < self.exploration_rate:
            return abs(hash((episode, state, "explore"))) % len(POSITION_ACTIONS)
        return max(range(len(values)), key=lambda index: values[index])

    @staticmethod
    def _reward(records: list[dict[str, Any]], index: int, target_position_pct: float) -> float:
        close = _as_float(records[index].get("close_price"))
        next_close = _as_float(records[index + 1].get("close_price"))
        if close <= 0:
            return 0.0
        next_return = (next_close / close) - 1
        turnover_penalty = 0.0005 if target_position_pct not in {0.0, 1.0} else 0.0002
        drawdown_penalty = max(0.0, -next_return) * target_position_pct * 0.2
        return target_position_pct * next_return - turnover_penalty - drawdown_penalty


class RLTrainingService:
    def __init__(self, db: Session, registry: RLModelRegistry | None = None) -> None:
        self.db = db
        self.registry = registry or RLModelRegistry()

    def list_scope_options(self) -> dict[str, Any]:
        return {
            "scopes": [
                {"key": "watchlist", "label": "全部自选池", "description": "使用当前自选股列表中的全部标的。"},
                {"key": "special_attention", "label": "重点关注池", "description": "使用自选股中标记为特别关注的标的。"},
                {"key": "smart_selection", "label": "券商推荐池 Top", "description": "优先使用最近一次智能选股落库的券商推荐池，并按推荐次数排序。"},
                {"key": "manual", "label": "手动输入", "description": "使用界面中手动填写的股票代码。"},
            ]
        }

    def resolve_symbols(self, *, scope: RLTrainingScope, symbols: list[str] | None = None, limit: int = 50) -> list[RLTrainingSymbol]:
        limit = max(1, min(limit, 300))
        resolved: list[RLTrainingSymbol]
        if scope == "watchlist":
            rows = self.db.scalars(
                select(WatchlistItem)
                .where(WatchlistItem.tenant_id == settings.default_tenant_id)
                .order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
                .limit(limit)
            ).all()
            resolved = [RLTrainingSymbol(item.symbol, security_name(item.symbol), "watchlist") for item in rows]
        elif scope == "special_attention":
            rows = self.db.scalars(
                select(WatchlistItem)
                .where(
                    WatchlistItem.tenant_id == settings.default_tenant_id,
                    WatchlistItem.is_special_attention.is_(True),
                )
                .order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
                .limit(limit)
            ).all()
            resolved = [RLTrainingSymbol(item.symbol, security_name(item.symbol), "special_attention") for item in rows]
        elif scope == "smart_selection":
            run = self.db.scalar(
                select(SmartSelectionRun)
                .where(
                    SmartSelectionRun.tenant_id == settings.default_tenant_id,
                    SmartSelectionRun.status == SmartSelectionRunStatus.SUCCEEDED,
                )
                .order_by(desc(SmartSelectionRun.started_at), desc(SmartSelectionRun.id))
                .limit(1)
            )
            if run is None:
                resolved = []
            else:
                institution_items = self.db.scalars(
                    select(SmartSelectionInstitutionPoolItem)
                    .where(SmartSelectionInstitutionPoolItem.run_id == run.id)
                    .order_by(
                        desc(SmartSelectionInstitutionPoolItem.recommend_count),
                        desc(SmartSelectionInstitutionPoolItem.rating_date),
                        SmartSelectionInstitutionPoolItem.id.asc(),
                    )
                    .limit(limit)
                ).all()
                if institution_items:
                    resolved = [
                        RLTrainingSymbol(item.symbol, item.name, f"institution_recommendation:{item.recommend_count}")
                        for item in institution_items
                    ]
                else:
                    items = self.db.scalars(
                        select(SmartSelectionItem)
                        .where(SmartSelectionItem.run_id == run.id)
                        .order_by(desc(SmartSelectionItem.score), SmartSelectionItem.id.asc())
                        .limit(limit)
                    ).all()
                    resolved = [RLTrainingSymbol(item.symbol, item.name, "smart_selection") for item in items]
        else:
            resolved = [RLTrainingSymbol(normalize_a_share_symbol(item), security_name(normalize_a_share_symbol(item)), "manual") for item in symbols or []]
        return self._dedupe_symbols(resolved)[:limit]

    def train(
        self,
        *,
        model_name: str,
        scope: RLTrainingScope,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        exclude_suspended: bool = True,
        limit: int = 50,
        episodes: int = 25,
        learning_rate: float = 0.2,
        discount_factor: float = 0.9,
        exploration_rate: float = 0.1,
        initial_cash: float = 100000.0,
        commission_rate: float = 0.0003,
        slippage_rate: float = 0.0002,
        reward_mode: str = "net_worth_change",
        max_position_pct: float = 1.0,
        ma_short_window: int = 5,
        ma_long_window: int = 20,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        start_date = self._coerce_date(start_date)
        end_date = self._coerce_date(end_date)
        self._emit_progress(progress_callback, 1, 6, "解析训练范围")
        resolved = self.resolve_symbols(scope=scope, symbols=symbols, limit=limit)
        normalized_symbols = [item.symbol for item in resolved if item.symbol]
        if not normalized_symbols:
            raise ValueError("training scope resolved no symbols")

        self._emit_progress(progress_callback, 2, 6, "加载历史日线数据")
        dataset = RLDatasetBuilder(self.db).build_dataset(
            symbols=normalized_symbols,
            start_date=start_date,
            end_date=end_date,
            source=source,
            adjustflag=adjustflag,
            exclude_suspended=exclude_suspended,
        )
        records_by_symbol = self._records_by_symbol(dataset.records)
        trainable_records = {symbol: records for symbol, records in records_by_symbol.items() if len(records) >= 22}
        if not trainable_records:
            raise ValueError("no symbols have enough daily bars for training")

        trainer = TabularQLearningTrainer(
            learning_rate=learning_rate,
            discount_factor=discount_factor,
            exploration_rate=exploration_rate,
            episodes=episodes,
        )
        def trainer_progress(step: int, total: int, label: str) -> None:
            self._emit_progress(progress_callback, 2 + step, 2 + total + 3, label)

        model = trainer.train(trainable_records, progress_callback=trainer_progress)
        self._emit_progress(progress_callback, 4, 6, "回放评估模型")
        policy = TabularRLPolicy(model["q_table"])
        config = RLEpisodeConfig(
            initial_cash=initial_cash,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            reward_mode=reward_mode,  # type: ignore[arg-type]
            max_position_pct=max_position_pct,
            ma_short_window=ma_short_window,
            ma_long_window=ma_long_window,
        )
        evaluations = []
        for symbol, records in trainable_records.items():
            actions = [policy.action_for_record(records, index) for index in range(len(records))]
            result = RLEpisodeSimulator(config).simulate(records, action_sequence=actions)
            evaluations.append(self._evaluation_summary(symbol, result.to_dict()))

        metrics = self._aggregate_metrics(evaluations)
        validation = self._validate_metrics(metrics)
        status: RLModelStatus = "validated" if validation["passed"] else "draft"
        model_id = f"rl-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC).isoformat()
        artifact = {
            "model_id": model_id,
            "name": model_name.strip() or model_id,
            "status": status,
            "algorithm": model["algorithm"],
            "created_at": now,
            "updated_at": now,
            "scope": scope,
            "symbols": [symbol_to_dict(item) for item in resolved],
            "config": {
                "source": source,
                "adjustflag": adjustflag,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "exclude_suspended": exclude_suspended,
                "limit": limit,
                "initial_cash": initial_cash,
                "commission_rate": commission_rate,
                "slippage_rate": slippage_rate,
                "reward_mode": reward_mode,
                "max_position_pct": max_position_pct,
                "ma_short_window": ma_short_window,
                "ma_long_window": ma_long_window,
            },
            "training": model,
            "metrics": metrics,
            "validation": validation,
            "evaluations": evaluations,
            "dataset_manifest": dataset.manifest,
        }
        self._emit_progress(progress_callback, 6, 6, "保存模型产物")
        return self.registry.save(artifact)

    def list_models(self) -> list[dict[str, Any]]:
        return self.registry.list_models()

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        return self.registry.load(model_id)

    def update_model_status(self, model_id: str, status: RLModelStatus) -> dict[str, Any] | None:
        artifact = self.registry.load(model_id)
        if artifact is None:
            return None
        validation = artifact.get("validation") or {}
        if status == "active" and not validation.get("passed", False):
            raise ValueError("model must pass validation before activation")
        return self.registry.update_status(model_id, status)

    @staticmethod
    def _coerce_date(value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str) and value:
            return date.fromisoformat(value)
        return None

    @staticmethod
    def _emit_progress(callback: Any | None, step: int, total: int, label: str) -> None:
        if callback is not None:
            callback(step, total, label)

    @staticmethod
    def _validate_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
        blockers: list[str] = []
        if int(metrics.get("evaluated_symbol_count") or 0) <= 0:
            blockers.append("no_evaluated_symbols")
        if int(metrics.get("trade_count") or 0) <= 0:
            blockers.append("no_trades")
        if float(metrics.get("avg_max_drawdown_pct") or 0) > 50:
            blockers.append("drawdown_too_high")
        if float(metrics.get("avg_total_return_pct") or 0) < -20:
            blockers.append("return_too_low")
        return {
            "passed": not blockers,
            "blockers": blockers,
            "rules": {
                "min_trade_count": 1,
                "max_avg_drawdown_pct": 50,
                "min_avg_total_return_pct": -20,
            },
        }

    @staticmethod
    def _dedupe_symbols(items: list[RLTrainingSymbol]) -> list[RLTrainingSymbol]:
        seen: set[str] = set()
        result: list[RLTrainingSymbol] = []
        for item in items:
            symbol = normalize_a_share_symbol(item.symbol)
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            result.append(RLTrainingSymbol(symbol=symbol, name=item.name or security_name(symbol), source=item.source))
        return result

    @staticmethod
    def _records_by_symbol(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            grouped[str(record["symbol"])].append(record)
        return {symbol: sorted(items, key=lambda item: str(item["trade_date"])) for symbol, items in grouped.items()}

    @staticmethod
    def _evaluation_summary(symbol: str, result: dict[str, Any]) -> dict[str, Any]:
        actions = result.get("actions", [])
        trade_count = sum(1 for action in actions if int(action.get("shares_delta") or 0) != 0)
        return {
            "symbol": symbol,
            "status": result.get("status"),
            "records": result.get("summary", {}).get("records", 0),
            "total_return_pct": result.get("total_return_pct", 0.0),
            "max_drawdown_pct": result.get("max_drawdown_pct", 0.0),
            "total_reward": result.get("total_reward", 0.0),
            "total_fees": result.get("total_fees", 0.0),
            "trade_count": trade_count,
            "risk_metrics": result.get("summary", {}).get("risk_metrics", {}),
        }

    @staticmethod
    def _aggregate_metrics(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
        if not evaluations:
            return {
                "evaluated_symbol_count": 0,
                "avg_total_return_pct": 0.0,
                "avg_max_drawdown_pct": 0.0,
                "trade_count": 0,
                "best_symbol": None,
                "worst_symbol": None,
            }
        sorted_by_return = sorted(evaluations, key=lambda item: float(item.get("total_return_pct") or 0), reverse=True)
        return {
            "evaluated_symbol_count": len(evaluations),
            "avg_total_return_pct": round(sum(float(item.get("total_return_pct") or 0) for item in evaluations) / len(evaluations), 6),
            "avg_max_drawdown_pct": round(sum(float(item.get("max_drawdown_pct") or 0) for item in evaluations) / len(evaluations), 6),
            "trade_count": sum(int(item.get("trade_count") or 0) for item in evaluations),
            "best_symbol": sorted_by_return[0]["symbol"],
            "worst_symbol": sorted_by_return[-1]["symbol"],
        }


class RLTrainingJobRegistry:
    _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rl-training")
    _lock = threading.Lock()

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[3] / "artifacts" / "rl_training_jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = f"job-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC).isoformat()
        status = {
            "job_id": job_id,
            "status": "queued",
            "progress_step": 0,
            "progress_total": 1,
            "progress_pct": 0.0,
            "progress_label": "排队中",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "model_id": None,
            "model": None,
            "error": None,
            "payload": payload,
        }
        self._write_status(status)
        self._executor.submit(self._run_job, job_id, payload)
        return status

    def get(self, job_id: str) -> dict[str, Any] | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _run_job(self, job_id: str, payload: dict[str, Any]) -> None:
        self._update(job_id, status="running", progress_step=0, progress_total=1, progress_pct=0.0, progress_label="开始训练", started_at=datetime.now(UTC).isoformat())

        def progress(step: int, total: int, label: str) -> None:
            pct = round((step / max(total, 1)) * 100, 2)
            self._update(job_id, progress_step=step, progress_total=total, progress_pct=pct, progress_label=label)

        try:
            with SessionLocal() as db:
                model = RLTrainingService(db).train(**payload, progress_callback=progress)
            self._update(
                job_id,
                status="succeeded",
                progress_step=1,
                progress_total=1,
                progress_pct=100.0,
                progress_label="训练完成",
                finished_at=datetime.now(UTC).isoformat(),
                model_id=model.get("model_id"),
                model=model,
                error=None,
            )
        except Exception as error:
            self._update(
                job_id,
                status="failed",
                progress_pct=100.0,
                progress_label="训练失败",
                finished_at=datetime.now(UTC).isoformat(),
                error=str(error),
            )

    def _update(self, job_id: str, **updates: Any) -> None:
        current = self.get(job_id) or {"job_id": job_id}
        current.update(updates)
        current["updated_at"] = datetime.now(UTC).isoformat()
        self._write_status(current)

    def _write_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._path(str(payload["job_id"])).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )

    def _path(self, job_id: str) -> Path:
        safe_job_id = "".join(ch for ch in job_id if ch.isalnum() or ch in {"-", "_"})
        return self.root / f"{safe_job_id}.json"


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _moving_average(records: list[dict[str, Any]], index: int, window: int) -> float | None:
    if index + 1 < window:
        return None
    values = [_as_float(item.get("close_price")) for item in records[index + 1 - window : index + 1]]
    return sum(values) / window if values else None


def _volume_ratio(records: list[dict[str, Any]], index: int, window: int) -> float:
    if index + 1 < window:
        return 1.0
    current = _as_float(records[index].get("volume"))
    values = [_as_float(item.get("volume")) for item in records[index + 1 - window : index + 1]]
    average = sum(values) / len(values) if values else 0.0
    return current / average if average > 0 else 1.0


def _volatility(records: list[dict[str, Any]], index: int, window: int) -> float:
    if index + 1 < window:
        return 0.0
    closes = [_as_float(item.get("close_price")) for item in records[index + 1 - window : index + 1]]
    returns = []
    for previous, current in zip(closes, closes[1:]):
        if previous > 0:
            returns.append(current / previous - 1)
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    return math.sqrt(sum((item - mean) ** 2 for item in returns) / len(returns))
