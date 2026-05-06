from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.market.baostock_sync_service import BaoStockHistorySyncService, BaoStockSyncResult
from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot, PriceHistoryProvider
from app.market.providers.eastmoney import EastMoneyQuoteProvider
from app.market.providers.sina import SinaDailyBarProvider
from app.market.providers.tencent import TencentDailyBarProvider
from app.market.rl_dataset_service import RLDatasetBuilder
from app.market.security_names import security_name
from app.market.symbols import normalize_a_share_symbol
from app.models.smart_selection_item import SmartSelectionItem
from app.models.smart_selection_institution_pool_item import SmartSelectionInstitutionPoolItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus
from app.models.watchlist import WatchlistItem
from app.quant.ppo_training import PPO_ALGORITHM, PPODatasetSplit, PPOTrainingConfig, PPOTradingTrainer, load_ppo_model, predict_ppo_action, split_records_by_symbol
from app.quant.simulator import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_DRAWDOWN_PENALTY_COEF,
    DEFAULT_INITIAL_CASH,
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_REWARD_MODE,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TURNOVER_PENALTY_COEF,
    RLEpisodeConfig,
    RLEpisodeSimulator,
)

RLTrainingScope = Literal["watchlist", "special_attention", "smart_selection", "manual"]
RLModelStatus = Literal["draft", "validated", "active", "retired"]
RLTrainingJobStatus = Literal["queued", "running", "succeeded", "failed"]

MIN_TRAINING_DAILY_BARS = 22
MIN_VALIDATED_TRAINABLE_SYMBOLS = 5
MIN_VALIDATED_TRAINABLE_RATIO = 0.3
MIN_VALIDATED_TRANSITIONS_WARNING = 10000
MIN_VALIDATED_TRANSITIONS_BLOCKER = 1000
DEFAULT_TRAINING_SYNC_LOOKBACK_DAYS = 730
FALLBACK_HISTORY_PROVIDERS: tuple[type[PriceHistoryProvider], ...] = (TencentDailyBarProvider, SinaDailyBarProvider, EastMoneyQuoteProvider)


class RLTrainingDataError(ValueError):
    def __init__(self, message: str, *, progress_details: list[str] | None = None) -> None:
        super().__init__(message)
        self.progress_details = progress_details or [message]


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
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

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


def symbol_to_dict(item: RLTrainingSymbol) -> dict[str, Any]:
    return {"symbol": item.symbol, "name": item.name, "source": item.source}


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

    def resolve_symbols(
        self,
        *,
        scope: RLTrainingScope = "watchlist",
        scopes: Sequence[RLTrainingScope] | None = None,
        symbols: list[str] | None = None,
        limit: int = 50,
    ) -> list[RLTrainingSymbol]:
        limit = max(1, min(limit, 300))
        selected_scopes = self._normalize_scopes(scope=scope, scopes=scopes)
        if len(selected_scopes) > 1:
            merged: list[RLTrainingSymbol] = []
            for selected_scope in selected_scopes:
                merged.extend(self.resolve_symbols(scope=selected_scope, symbols=symbols, limit=limit))
            return self._dedupe_symbols(merged)[:limit]

        scope = selected_scopes[0]
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

    @staticmethod
    def _normalize_scopes(*, scope: RLTrainingScope = "watchlist", scopes: Sequence[RLTrainingScope] | None = None) -> list[RLTrainingScope]:
        selected = list(scopes or []) or [scope]
        normalized: list[RLTrainingScope] = []
        for item in selected:
            if item in normalized:
                continue
            normalized.append(item)
        return normalized or [scope]

    def train(
        self,
        *,
        model_name: str,
        scope: RLTrainingScope,
        scopes: Sequence[RLTrainingScope] | None = None,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        exclude_suspended: bool = True,
        limit: int = 50,
        initial_cash: float = DEFAULT_INITIAL_CASH,
        commission_rate: float = DEFAULT_COMMISSION_RATE,
        slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
        reward_mode: str = DEFAULT_REWARD_MODE,
        max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
        ma_short_window: int = 5,
        ma_long_window: int = 20,
        algorithm: str = PPO_ALGORITHM,
        total_timesteps: int = 100000,
        train_split_pct: float = 0.8,
        ppo_n_steps: int = 512,
        ppo_batch_size: int = 64,
        ppo_learning_rate: float = 0.00031,
        drawdown_penalty_coef: float = DEFAULT_DRAWDOWN_PENALTY_COEF,
        turnover_penalty_coef: float = DEFAULT_TURNOVER_PENALTY_COEF,
        min_validation_bars: int = 5,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        start_date = self._coerce_date(start_date)
        end_date = self._coerce_date(end_date)
        selected_scopes = self._normalize_scopes(scope=scope, scopes=scopes)
        self._emit_progress(
            progress_callback,
            1,
            8,
            "解析训练范围",
            [f"训练范围：{'+'.join(selected_scopes)}", f"标的上限：{limit}"],
        )
        resolved = self.resolve_symbols(scope=scope, scopes=selected_scopes, symbols=symbols, limit=limit)
        normalized_symbols = [item.symbol for item in resolved if item.symbol]
        if not normalized_symbols:
            raise ValueError("training scope resolved no symbols")

        self._emit_progress(
            progress_callback,
            2,
            8,
            "加载本地历史日线",
            [f"候选标的：{len(normalized_symbols)} 只", f"日期范围：{start_date or '不限'} ~ {end_date or '今天'}"],
        )
        dataset = self._build_training_dataset(
            symbols=normalized_symbols,
            start_date=start_date,
            end_date=end_date,
            source=source,
            adjustflag=adjustflag,
            exclude_suspended=exclude_suspended,
        )
        records_by_symbol = self._records_by_symbol(dataset.records)
        trainable_records = self._trainable_records(records_by_symbol, normalized_symbols)
        missing_training_symbols = self._missing_training_symbols(records_by_symbol, normalized_symbols)
        sync_diagnostics: dict[str, Any] | None = None
        if missing_training_symbols and source == "baostock":
            self._emit_progress(
                progress_callback,
                3,
                8,
                "本地日线不足，自动同步历史数据",
                [
                    "主源：BaoStock",
                    "兜底：腾讯 → 新浪 → 东方财富",
                    f"候选标的：{len(normalized_symbols)} 只",
                    f"需补齐标的：{len(missing_training_symbols)} 只",
                ],
            )
            sync_diagnostics = self._sync_missing_training_history(
                symbols=missing_training_symbols,
                start_date=start_date,
                end_date=end_date,
                adjustflag=adjustflag,
                progress_callback=progress_callback,
            )
            dataset = self._build_training_dataset(
                symbols=normalized_symbols,
                start_date=start_date,
                end_date=end_date,
                source=source,
                adjustflag=adjustflag,
                exclude_suspended=exclude_suspended,
            )
            records_by_symbol = self._records_by_symbol(dataset.records)
            trainable_records = self._trainable_records(records_by_symbol, normalized_symbols)
            self._emit_progress(
                progress_callback,
                4,
                8,
                "同步后重新加载训练集",
                [f"数据行数：{dataset.count}", f"可训练标的：{len(trainable_records)} / {len(normalized_symbols)}"],
            )
        if not trainable_records:
            raise ValueError(self._insufficient_daily_bars_message(records_by_symbol, normalized_symbols, sync_diagnostics))

        coverage_metrics = self._training_coverage_metrics(
            records_by_symbol=records_by_symbol,
            trainable_records=trainable_records,
            symbols=normalized_symbols,
            dataset_count=dataset.count,
        )
        self._emit_progress(
            progress_callback,
            4,
            8,
            "训练集准备完成",
            [
                f"数据行数：{dataset.count}",
                f"可训练标的：{len(trainable_records)} / {len(normalized_symbols)}",
                f"覆盖率：{coverage_metrics['trainable_symbol_ratio'] * 100:.1f}%",
                f"最少日线要求：{MIN_TRAINING_DAILY_BARS}",
            ],
        )
        model_id = f"rl-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        model_dir = self.registry.root / model_id
        selected_algorithm = PPO_ALGORITHM
        config = RLEpisodeConfig(
            initial_cash=initial_cash,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            reward_mode=reward_mode,  # type: ignore[arg-type]
            max_position_pct=max_position_pct,
            ma_short_window=ma_short_window,
            ma_long_window=ma_long_window,
            drawdown_penalty_coef=drawdown_penalty_coef,
            turnover_penalty_coef=turnover_penalty_coef,
        )

        ppo_config = PPOTrainingConfig(
            total_timesteps=total_timesteps,
            train_split_pct=train_split_pct,
            n_steps=ppo_n_steps,
            batch_size=ppo_batch_size,
            learning_rate=ppo_learning_rate,
            initial_cash=initial_cash,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            reward_mode=reward_mode,  # type: ignore[arg-type]
            max_position_pct=max_position_pct,
            drawdown_penalty_coef=drawdown_penalty_coef,
            turnover_penalty_coef=turnover_penalty_coef,
            min_validation_bars=min_validation_bars,
        )

        def ppo_progress(step: int, total: int, label: str, details: list[str] | None = None) -> None:
            self._emit_progress(progress_callback, 4 + step, 4 + total + 3, label, details)

        split = split_records_by_symbol(trainable_records, train_split_pct, min_validation_bars=min_validation_bars)
        split_diagnostics = self._ppo_split_diagnostics(
            split=split,
            records_by_symbol=trainable_records,
            resolved_symbol_count=len(normalized_symbols),
            dataset_count=dataset.count,
            trainable_symbol_count=len(trainable_records),
        )
        if not split.train:
            message = self._insufficient_ppo_split_message(split_diagnostics, min_validation_bars)
            raise RLTrainingDataError(message, progress_details=self._ppo_split_progress_details(message, split_diagnostics))

        self._emit_progress(
            progress_callback,
            5,
            8,
            "训练 PPO 深度模型",
            [f"训练步数：{total_timesteps}", f"训练标的：{len(trainable_records)} 只", *self._ppo_split_progress_details("PPO 数据切分快照", split_diagnostics)[1:]],
        )
        try:
            model = PPOTradingTrainer(ppo_config).train(trainable_records, model_path=model_dir / "policy.zip", progress_callback=ppo_progress, dataset_split=split)
        except Exception as error:
            message = self._ppo_failure_message(str(error), split_diagnostics)
            raise RLTrainingDataError(message, progress_details=self._ppo_split_progress_details(message, split_diagnostics)) from error
        policy_model = load_ppo_model(model_dir / "policy.zip")
        train_evaluations = self._evaluate_ppo_policy(split.train, policy_model, ppo_config, config, progress_callback=progress_callback, split_name="train")
        validation_evaluations = self._evaluate_ppo_policy(split.validation, policy_model, ppo_config, config, progress_callback=progress_callback, split_name="validation")
        full_evaluations = self._evaluate_ppo_policy(trainable_records, policy_model, ppo_config, config, progress_callback=progress_callback, split_name="full")
        evaluations = validation_evaluations or train_evaluations
        split_metrics = {
            "train": self._aggregate_metrics(train_evaluations),
            "validation": self._aggregate_metrics(validation_evaluations),
            "full": self._aggregate_metrics(full_evaluations),
        }
        model.setdefault("splits", split.metadata)

        self._emit_progress(progress_callback, 7, 8, "汇总验证指标", [f"已评估标的：{len(evaluations)} 只"])
        metrics = self._aggregate_metrics(evaluations)
        if split_metrics:
            metrics["splits"] = split_metrics
            metrics["validation"] = split_metrics.get("validation", {})
            metrics["validation_trade_count"] = int(split_metrics.get("validation", {}).get("trade_count") or 0)
            metrics["validation_evaluated_symbol_count"] = int(split_metrics.get("validation", {}).get("evaluated_symbol_count") or 0)
            metrics["validation_excess_return_pct"] = float(split_metrics.get("validation", {}).get("avg_excess_return_pct") or 0.0)
            metrics["validation_max_drawdown_pct"] = float(split_metrics.get("validation", {}).get("avg_max_drawdown_pct") or 0.0)
        metrics.update(coverage_metrics)
        metrics["training_transition_count"] = int(model.get("transitions") or model.get("total_timesteps") or 0)
        validation = self._validate_metrics(metrics)
        status: RLModelStatus = "validated" if validation["passed"] else "draft"
        now = datetime.now(UTC).isoformat()
        artifact = {
            "model_id": model_id,
            "name": model_name.strip() or model_id,
            "status": status,
            "algorithm": model["algorithm"],
            "created_at": now,
            "updated_at": now,
            "scope": "+".join(selected_scopes),
            "symbols": [symbol_to_dict(item) for item in resolved],
            "config": {
                "algorithm": selected_algorithm,
                "source": source,
                "adjustflag": adjustflag,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "exclude_suspended": exclude_suspended,
                "limit": limit,
                "scopes": list(selected_scopes),
                "initial_cash": initial_cash,
                "commission_rate": commission_rate,
                "slippage_rate": slippage_rate,
                "reward_mode": reward_mode,
                "max_position_pct": max_position_pct,
                "ma_short_window": ma_short_window,
                "ma_long_window": ma_long_window,
                "total_timesteps": total_timesteps,
                "train_split_pct": train_split_pct,
                "ppo_n_steps": ppo_n_steps,
                "ppo_batch_size": ppo_batch_size,
                "ppo_learning_rate": ppo_learning_rate,
                "drawdown_penalty_coef": drawdown_penalty_coef,
                "turnover_penalty_coef": turnover_penalty_coef,
                "min_validation_bars": min_validation_bars,
            },
            "training": model,
            "splits": model.get("splits", {}),
            "metrics": metrics,
            "validation": validation,
            "evaluations": evaluations,
            "dataset_manifest": dataset.manifest,
        }
        self._emit_progress(
            progress_callback,
            8,
            8,
            "保存模型产物",
            [
                f"模型状态：{status}",
                f"可训练覆盖：{metrics.get('trainable_symbol_count', 0)} / {metrics.get('candidate_symbol_count', 0)}",
                f"状态转移：{metrics.get('training_transition_count', 0)}",
                f"交易次数：{metrics.get('trade_count', 0)}",
                f"平均收益：{metrics.get('avg_total_return_pct', 0)}%",
            ],
        )
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
    def _emit_progress(callback: Any | None, step: int, total: int, label: str, details: list[str] | None = None) -> None:
        if callback is not None:
            callback(step, total, label, details or [])

    def _build_training_dataset(
        self,
        *,
        symbols: list[str],
        start_date: date | None,
        end_date: date | None,
        source: str,
        adjustflag: str,
        exclude_suspended: bool,
    ):
        return RLDatasetBuilder(self.db).build_dataset(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            source=source,
            adjustflag=adjustflag,
            exclude_suspended=exclude_suspended,
        )

    def _sync_missing_training_history(
        self,
        *,
        symbols: list[str],
        start_date: date | None,
        end_date: date | None,
        adjustflag: str,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        sync_end_date = end_date or date.today()
        sync_start_date = start_date or sync_end_date - timedelta(days=DEFAULT_TRAINING_SYNC_LOOKBACK_DAYS)
        self._emit_progress(
            progress_callback,
            3,
            8,
            "同步 BaoStock 历史日线",
            [f"日期范围：{sync_start_date} ~ {sync_end_date}", f"标的数量：{len(symbols)}"],
        )
        try:
            def sync_progress(step: int, total: int, label: str, details: list[str] | None = None) -> None:
                self._emit_progress(
                    progress_callback,
                    3,
                    8,
                    label,
                    [f"BaoStock 同步进度：{step} / {total}", *(details or [])],
                )

            result = BaoStockHistorySyncService(self.db).sync_history(
                symbols=symbols,
                start_date=sync_start_date,
                end_date=sync_end_date,
                adjustflag=adjustflag,
                incremental=True,
                progress_callback=sync_progress,
            )
        except Exception as error:
            raise ValueError(f"failed to sync BaoStock history for RL training: {error}") from error
        diagnostics = self._sync_diagnostics(result)
        if int(diagnostics.get("bars_upserted") or 0) <= 0:
            fallback = self._sync_training_history_from_fallback_providers(
                symbols=symbols,
                start_date=sync_start_date,
                end_date=sync_end_date,
                adjustflag=adjustflag,
                progress_callback=progress_callback,
            )
            diagnostics["fallback_sync"] = fallback
        return diagnostics

    def _sync_training_history_from_fallback_providers(
        self,
        *,
        symbols: list[str],
        start_date: date,
        end_date: date,
        adjustflag: str,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        limit = max(MIN_TRAINING_DAILY_BARS, min(1200, (end_date - start_date).days + 40))
        storage = MarketDailyBarStorage(self.db)
        succeeded_symbols: list[str] = []
        failures: list[dict[str, str]] = []
        bars_upserted = 0
        providers = [provider_class() for provider_class in FALLBACK_HISTORY_PROVIDERS]

        total_symbols = len(symbols)
        for symbol_index, symbol in enumerate(symbols, start=1):
            symbol_failures: list[str] = []
            for provider in providers:
                self._emit_progress(
                    progress_callback,
                    3,
                    8,
                    f"备用源同步 {symbol_index}/{total_symbols}",
                    [
                        f"当前标的：{symbol}",
                        f"进度：{symbol_index}/{total_symbols}",
                        f"尝试数据源：{provider.name}",
                        f"请求日线数量：{limit}",
                    ],
                )
                try:
                    bars = provider.fetch_daily_bars(symbol, limit=limit)
                except Exception as error:
                    symbol_failures.append(f"{provider.name}: {error}")
                    continue
                filtered_bars = self._training_compatible_fallback_bars(bars, start_date=start_date, end_date=end_date)
                if not filtered_bars:
                    symbol_failures.append(f"{provider.name}: no bars in selected date range")
                    continue
                written = storage.upsert_bars(filtered_bars, source="baostock", adjustflag=adjustflag)
                bars_upserted += written
                succeeded_symbols.append(symbol)
                self._emit_progress(
                    progress_callback,
                    3,
                    8,
                    f"备用源同步 {symbol_index}/{total_symbols}",
                    [
                        f"当前标的：{symbol}",
                        f"进度：{symbol_index}/{total_symbols}",
                        f"命中数据源：{provider.name}",
                        f"写入日线：{written} 条",
                    ],
                )
                break
            if symbol not in succeeded_symbols:
                reason = "; ".join(symbol_failures) or "no fallback provider returned bars"
                failures.append({"symbol": symbol, "reason": reason})
                self._emit_progress(
                    progress_callback,
                    3,
                    8,
                    f"备用源同步 {symbol_index}/{total_symbols}",
                    [f"当前标的：{symbol}", f"进度：{symbol_index}/{total_symbols}", f"同步失败：{reason[:120]}"],
                )

        status = "completed"
        if failures and succeeded_symbols:
            status = "partial_success"
        elif failures:
            status = "failed"
        return {
            "status": status,
            "source": "fallback:tencent,sina,eastmoney",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "success_count": len(succeeded_symbols),
            "failure_count": len(failures),
            "bars_upserted": bars_upserted,
            "succeeded_symbols": succeeded_symbols,
            "failures": failures[:5],
        }

    @staticmethod
    def _training_compatible_fallback_bars(
        bars: list[DailyBarSnapshot],
        *,
        start_date: date,
        end_date: date,
    ) -> list[DailyBarSnapshot]:
        compatible: list[DailyBarSnapshot] = []
        for bar in bars:
            if bar.trade_date < start_date or bar.trade_date > end_date:
                continue
            compatible.append(replace(bar, trade_status=1, is_st=bar.is_st or False))
        return compatible

    @staticmethod
    def _sync_diagnostics(result: Any) -> dict[str, Any]:
        if isinstance(result, BaoStockSyncResult):
            payload = result.to_dict()
        elif hasattr(result, "to_dict"):
            payload = result.to_dict()
        elif isinstance(result, dict):
            payload = result
        else:
            payload = {}
        failures = list(payload.get("failures") or [])
        return {
            "status": payload.get("status"),
            "source": payload.get("source"),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "success_count": payload.get("success_count"),
            "failure_count": payload.get("failure_count"),
            "bars_upserted": payload.get("bars_upserted"),
            "failures": failures[:5],
        }

    @staticmethod
    def _missing_training_symbols(
        records_by_symbol: dict[str, list[dict[str, Any]]],
        symbols: list[str],
    ) -> list[str]:
        return [symbol for symbol in symbols if len(records_by_symbol.get(symbol, [])) < MIN_TRAINING_DAILY_BARS]

    @staticmethod
    def _trainable_records(
        records_by_symbol: dict[str, list[dict[str, Any]]],
        symbols: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            symbol: records_by_symbol.get(symbol, [])
            for symbol in symbols
            if len(records_by_symbol.get(symbol, [])) >= MIN_TRAINING_DAILY_BARS
        }

    @staticmethod
    def _training_coverage_metrics(
        *,
        records_by_symbol: dict[str, list[dict[str, Any]]],
        trainable_records: dict[str, list[dict[str, Any]]],
        symbols: list[str],
        dataset_count: int,
    ) -> dict[str, Any]:
        candidate_count = len(symbols)
        trainable_count = len(trainable_records)
        trainable_lengths = [len(records) for records in trainable_records.values()]
        untrainable = [symbol for symbol in symbols if symbol not in trainable_records]
        return {
            "candidate_symbol_count": candidate_count,
            "trainable_symbol_count": trainable_count,
            "trainable_symbol_ratio": round(trainable_count / candidate_count, 6) if candidate_count else 0.0,
            "dataset_row_count": int(dataset_count or 0),
            "min_trainable_daily_bars": min(trainable_lengths) if trainable_lengths else 0,
            "max_trainable_daily_bars": max(trainable_lengths) if trainable_lengths else 0,
            "avg_trainable_daily_bars": round(sum(trainable_lengths) / len(trainable_lengths), 2) if trainable_lengths else 0.0,
            "untrainable_symbol_count": len(untrainable),
            "untrainable_symbols_sample": untrainable[:10],
        }

    @staticmethod
    def _insufficient_daily_bars_message(
        records_by_symbol: dict[str, list[dict[str, Any]]],
        symbols: list[str],
        sync_diagnostics: dict[str, Any] | None = None,
    ) -> str:
        counts = {symbol: len(records_by_symbol.get(symbol, [])) for symbol in symbols}
        message = (
            "no symbols have enough daily bars for training; "
            f"minimum={MIN_TRAINING_DAILY_BARS}; counts={counts}"
        )
        if sync_diagnostics:
            message += f"; baostock_sync={sync_diagnostics}"
        range_hint = ""
        if sync_diagnostics and sync_diagnostics.get("start_date") and sync_diagnostics.get("end_date"):
            try:
                sync_start = date.fromisoformat(str(sync_diagnostics["start_date"]))
                sync_end = date.fromisoformat(str(sync_diagnostics["end_date"]))
                calendar_days = (sync_end - sync_start).days + 1
                if calendar_days < 60:
                    range_hint = f"; selected date range has only {calendar_days} calendar days, which is usually too short for 22 trading bars"
            except ValueError:
                range_hint = ""
        return message + range_hint + "; please sync BaoStock history or widen the training date range"

    @staticmethod
    def _insufficient_ppo_split_message(
        diagnostics: dict[str, Any],
        min_validation_bars: int,
    ) -> str:
        return (
            "no symbols have enough daily bars after train/validation split; "
            f"min_validation_bars={min_validation_bars}; "
            f"resolved_symbol_count={diagnostics['resolved_symbol_count']}; "
            f"dataset_count={diagnostics['dataset_count']}; "
            f"trainable_symbol_count={diagnostics['trainable_symbol_count']}; "
            f"split_train_symbol_count={diagnostics['split_train_symbol_count']}; "
            f"split_validation_symbol_count={diagnostics['split_validation_symbol_count']}; "
            f"sample={diagnostics['sample']}; "
            "please widen the training date range or lower min_validation_bars"
        )

    @staticmethod
    def _ppo_split_diagnostics(
        *,
        split: PPODatasetSplit,
        records_by_symbol: dict[str, list[dict[str, Any]]],
        resolved_symbol_count: int,
        dataset_count: int,
        trainable_symbol_count: int,
    ) -> dict[str, Any]:
        sample: dict[str, dict[str, Any]] = {}
        for symbol in sorted(records_by_symbol)[:10]:
            metadata = split.metadata.get(symbol, {})
            sample[symbol] = {
                "daily_bars": len(records_by_symbol.get(symbol, [])),
                "included_in_training": metadata.get("included_in_training"),
                "excluded_reason": metadata.get("excluded_reason"),
                "total_bars": metadata.get("total_bars"),
                "train_bars": metadata.get("train_bars"),
                "validation_bars": metadata.get("validation_bars"),
                "min_validation_bars": metadata.get("min_validation_bars"),
            }
        return {
            "resolved_symbol_count": resolved_symbol_count,
            "dataset_count": int(dataset_count or 0),
            "trainable_symbol_count": trainable_symbol_count,
            "split_train_symbol_count": len(split.train),
            "split_validation_symbol_count": len(split.validation),
            "sample": sample,
        }

    @staticmethod
    def _ppo_split_progress_details(message: str, diagnostics: dict[str, Any]) -> list[str]:
        return [
            message,
            f"resolved_symbol_count={diagnostics['resolved_symbol_count']}",
            f"dataset_count={diagnostics['dataset_count']}",
            f"trainable_symbol_count={diagnostics['trainable_symbol_count']}",
            f"split_train_symbol_count={diagnostics['split_train_symbol_count']}",
            f"split_validation_symbol_count={diagnostics['split_validation_symbol_count']}",
            f"split_sample={diagnostics['sample']}",
        ]

    @staticmethod
    def _ppo_failure_message(message: str, diagnostics: dict[str, Any]) -> str:
        if "no symbols have enough daily bars after train/validation split" not in message:
            return message
        return (
            f"{message}; "
            f"resolved_symbol_count={diagnostics['resolved_symbol_count']}; "
            f"dataset_count={diagnostics['dataset_count']}; "
            f"trainable_symbol_count={diagnostics['trainable_symbol_count']}; "
            f"split_train_symbol_count={diagnostics['split_train_symbol_count']}; "
            f"split_validation_symbol_count={diagnostics['split_validation_symbol_count']}; "
            f"sample={diagnostics['sample']}"
        )

    @staticmethod
    def _validate_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []
        candidate_count = int(metrics.get("candidate_symbol_count") or 0)
        trainable_count = int(metrics.get("trainable_symbol_count") or 0)
        trainable_ratio = float(metrics.get("trainable_symbol_ratio") or 0)
        transitions = int(metrics.get("training_transition_count") or 0)

        if int(metrics.get("evaluated_symbol_count") or 0) <= 0:
            blockers.append("no_evaluated_symbols")
        if candidate_count >= 10 and trainable_count < MIN_VALIDATED_TRAINABLE_SYMBOLS:
            blockers.append("trainable_symbols_too_few")
        if candidate_count >= 10 and trainable_ratio < MIN_VALIDATED_TRAINABLE_RATIO:
            blockers.append("trainable_coverage_too_low")
        if transitions < MIN_VALIDATED_TRANSITIONS_BLOCKER:
            blockers.append("training_sample_too_small")
        elif transitions < MIN_VALIDATED_TRANSITIONS_WARNING:
            warnings.append("training_sample_small")
        if int(metrics.get("trade_count") or 0) <= 0:
            blockers.append("no_trades")
        if "validation_evaluated_symbol_count" in metrics and int(metrics.get("validation_evaluated_symbol_count") or 0) <= 0:
            blockers.append("no_validation_symbols")
        if "validation_trade_count" in metrics and int(metrics.get("validation_trade_count") or 0) <= 0:
            blockers.append("validation_no_trades")
        if "validation_excess_return_pct" in metrics and float(metrics.get("validation_excess_return_pct") or 0) < -20:
            blockers.append("validation_excess_return_too_low")
        if "validation_max_drawdown_pct" in metrics and float(metrics.get("validation_max_drawdown_pct") or 0) > 50:
            blockers.append("validation_drawdown_too_high")
        if float(metrics.get("avg_max_drawdown_pct") or 0) > 50:
            blockers.append("drawdown_too_high")
        if float(metrics.get("avg_total_return_pct") or 0) < -20:
            blockers.append("return_too_low")
        return {
            "passed": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "rules": {
                "min_trade_count": 1,
                "max_avg_drawdown_pct": 50,
                "min_avg_total_return_pct": -20,
                "min_trainable_symbols_for_large_scope": MIN_VALIDATED_TRAINABLE_SYMBOLS,
                "min_trainable_ratio_for_large_scope": MIN_VALIDATED_TRAINABLE_RATIO,
                "large_scope_candidate_threshold": 10,
                "min_training_transitions": MIN_VALIDATED_TRANSITIONS_BLOCKER,
                "recommended_training_transitions": MIN_VALIDATED_TRANSITIONS_WARNING,
                "min_validation_trade_count": 1,
                "min_validation_excess_return_pct": -20,
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

    def _evaluate_ppo_policy(
        self,
        records_by_symbol: dict[str, list[dict[str, Any]]],
        policy_model: Any,
        ppo_config: PPOTrainingConfig,
        episode_config: RLEpisodeConfig,
        *,
        progress_callback: Any | None = None,
        split_name: str = "validation",
    ) -> list[dict[str, Any]]:
        evaluations: list[dict[str, Any]] = []
        total_symbols = len(records_by_symbol)
        for index, (symbol, records) in enumerate(records_by_symbol.items(), start=1):
            self._emit_progress(
                progress_callback,
                6,
                8,
                f"PPO {split_name} 回放 {index}/{total_symbols}",
                [f"当前阶段：{split_name}", f"当前标的：{symbol}", f"日线数量：{len(records)}"],
            )
            actions = []
            synthetic_artifact = {
                "model_id": "__in_memory__",
                "config": {
                    "initial_cash": ppo_config.initial_cash,
                    "commission_rate": ppo_config.commission_rate,
                    "slippage_rate": ppo_config.slippage_rate,
                    "reward_mode": ppo_config.reward_mode,
                    "max_position_pct": ppo_config.max_position_pct,
                },
                "training": {"policy_path": "policy.zip"},
            }
            for record_index in range(len(records)):
                if record_index == 0:
                    predicted = {"action_index": 0, "action_type": "hold", "target_position_pct": 0.0}
                else:
                    predicted = predict_ppo_action(synthetic_artifact, records[: record_index + 1], model=policy_model)
                actions.append({
                    "trade_date": str(records[record_index]["trade_date"]),
                    "action": {
                        "action_type": predicted["action_type"],
                        "target_position_pct": predicted["target_position_pct"],
                    },
                    "action_index": predicted["action_index"],
                })
            result = RLEpisodeSimulator(episode_config).simulate(records, action_sequence=actions)
            summary = self._evaluation_summary(symbol, result.to_dict())
            summary["split"] = split_name
            evaluations.append(summary)
        return evaluations

    @staticmethod
    def _evaluation_summary(symbol: str, result: dict[str, Any]) -> dict[str, Any]:
        actions = result.get("actions", [])
        trade_actions = [action for action in actions if int(action.get("shares_delta") or 0) != 0]
        trade_count = len(trade_actions)
        trade_details = RLTrainingService._trade_details(symbol, trade_actions)
        return {
            "symbol": symbol,
            "status": result.get("status"),
            "records": result.get("summary", {}).get("records", 0),
            "benchmark_return_pct": result.get("summary", {}).get("benchmark_return_pct", 0.0),
            "excess_return_pct": round(float(result.get("total_return_pct") or 0.0) - float(result.get("summary", {}).get("benchmark_return_pct") or 0.0), 6),
            "total_return_pct": result.get("total_return_pct", 0.0),
            "max_drawdown_pct": result.get("max_drawdown_pct", 0.0),
            "total_reward": result.get("total_reward", 0.0),
            "total_fees": result.get("total_fees", 0.0),
            "trade_count": trade_count,
            "trade_details": trade_details,
            "trade_details_sample": trade_details[:20],
            "risk_metrics": result.get("summary", {}).get("risk_metrics", {}),
        }

    @staticmethod
    def _trade_details(symbol: str, trade_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        details: list[dict[str, Any]] = []
        open_lots: list[dict[str, Any]] = []
        sequence = 0
        for action in trade_actions:
            shares_delta = int(action.get("shares_delta") or 0)
            price = float(action.get("execution_price") or 0)
            fee = float(action.get("fee") or 0)
            trade_date = str(action.get("trade_date") or "")
            if shares_delta > 0:
                open_lots.append({
                    "trade_date": trade_date,
                    "shares": shares_delta,
                    "remaining_shares": shares_delta,
                    "price": price,
                    "fee": fee,
                })
                details.append({
                    "sequence": sequence + 1,
                    "symbol": symbol,
                    "side": "buy",
                    "trade_date": trade_date,
                    "shares": shares_delta,
                    "price": round(price, 6),
                    "amount": round(shares_delta * price, 4),
                    "fee": round(fee, 4),
                    "position_return_pct": None,
                    "realized_profit": None,
                    "holding_days": None,
                })
                sequence += 1
                continue

            shares_to_sell = abs(shares_delta)
            realized_cost = 0.0
            realized_buy_fees = 0.0
            sell_shares = shares_to_sell
            first_buy_date: str | None = None
            while shares_to_sell > 0 and open_lots:
                lot = open_lots[0]
                matched_shares = min(shares_to_sell, int(lot["remaining_shares"]))
                if first_buy_date is None:
                    first_buy_date = str(lot["trade_date"])
                realized_cost += matched_shares * float(lot["price"])
                realized_buy_fees += float(lot["fee"]) * matched_shares / max(int(lot["shares"]), 1)
                lot["remaining_shares"] = int(lot["remaining_shares"]) - matched_shares
                shares_to_sell -= matched_shares
                if int(lot["remaining_shares"]) <= 0:
                    open_lots.pop(0)

            proceeds = sell_shares * price
            realized_profit = proceeds - realized_cost - realized_buy_fees - fee
            denominator = realized_cost + realized_buy_fees
            holding_days = RLTrainingService._holding_days(first_buy_date, trade_date)
            details.append({
                "sequence": sequence + 1,
                "symbol": symbol,
                "side": "sell",
                "trade_date": trade_date,
                "shares": sell_shares,
                "price": round(price, 6),
                "amount": round(proceeds, 4),
                "fee": round(fee, 4),
                "matched_buy_date": first_buy_date,
                "realized_profit": round(realized_profit, 4),
                "position_return_pct": round(realized_profit / denominator * 100, 6) if denominator > 0 else None,
                "holding_days": holding_days,
            })
            sequence += 1
        return details

    @staticmethod
    def _holding_days(start_value: str | None, end_value: str) -> int | None:
        if not start_value or not end_value:
            return None
        try:
            return (date.fromisoformat(end_value) - date.fromisoformat(start_value)).days
        except ValueError:
            return None

    @staticmethod
    def _aggregate_metrics(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
        if not evaluations:
            return {
                "evaluated_symbol_count": 0,
                "avg_total_return_pct": 0.0,
                "avg_max_drawdown_pct": 0.0,
                "avg_benchmark_return_pct": 0.0,
                "avg_excess_return_pct": 0.0,
                "avg_annualized_return_pct": 0.0,
                "avg_annualized_volatility_pct": 0.0,
                "avg_sharpe_ratio": 0.0,
                "avg_sortino_ratio": 0.0,
                "avg_calmar_ratio": 0.0,
                "avg_win_rate_pct": 0.0,
                "avg_profit_loss_ratio": 0.0,
                "avg_trade_return_pct": 0.0,
                "avg_turnover_pct": 0.0,
                "avg_holding_days": 0.0,
                "trade_count": 0,
                "best_symbol": None,
                "worst_symbol": None,
            }
        sorted_by_return = sorted(evaluations, key=lambda item: float(item.get("total_return_pct") or 0), reverse=True)
        risk_metrics = [item.get("risk_metrics") or {} for item in evaluations]
        trade_details = [trade for item in evaluations for trade in item.get("trade_details", [])]
        sell_trades = [trade for trade in trade_details if trade.get("side") == "sell"]
        winning = [trade for trade in sell_trades if float(trade.get("realized_profit") or 0) > 0]
        losing = [trade for trade in sell_trades if float(trade.get("realized_profit") or 0) < 0]
        gross_profit = sum(float(trade.get("realized_profit") or 0) for trade in winning)
        gross_loss = abs(sum(float(trade.get("realized_profit") or 0) for trade in losing))
        holding_days = [int(trade.get("holding_days") or 0) for trade in sell_trades if trade.get("holding_days") is not None]

        def avg_metric(key: str) -> float:
            return round(sum(float(item.get(key) or 0) for item in risk_metrics) / len(risk_metrics), 6) if risk_metrics else 0.0

        return {
            "evaluated_symbol_count": len(evaluations),
            "avg_total_return_pct": round(sum(float(item.get("total_return_pct") or 0) for item in evaluations) / len(evaluations), 6),
            "avg_max_drawdown_pct": round(sum(float(item.get("max_drawdown_pct") or 0) for item in evaluations) / len(evaluations), 6),
            "avg_benchmark_return_pct": round(sum(float(item.get("benchmark_return_pct") or 0) for item in evaluations) / len(evaluations), 6),
            "avg_excess_return_pct": round(sum(float(item.get("excess_return_pct") or 0) for item in evaluations) / len(evaluations), 6),
            "avg_annualized_return_pct": avg_metric("annualized_return_pct"),
            "avg_annualized_volatility_pct": avg_metric("annualized_volatility_pct"),
            "avg_sharpe_ratio": avg_metric("sharpe_ratio"),
            "avg_sortino_ratio": avg_metric("sortino_ratio"),
            "avg_calmar_ratio": avg_metric("calmar_ratio"),
            "avg_win_rate_pct": avg_metric("win_rate_pct"),
            "avg_turnover_pct": avg_metric("turnover_pct"),
            "avg_profit_loss_ratio": round(gross_profit / gross_loss, 6) if gross_loss else 0.0,
            "avg_trade_return_pct": round(sum(float(trade.get("position_return_pct") or 0) for trade in sell_trades) / len(sell_trades), 6) if sell_trades else 0.0,
            "avg_holding_days": round(sum(holding_days) / len(holding_days), 2) if holding_days else 0.0,
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
            "progress_details": [],
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
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return self._normalize_job_payload(payload)

    def latest(self) -> dict[str, Any] | None:
        jobs: list[dict[str, Any]] = []
        for path in self.root.glob("job-*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                jobs.append(self._normalize_job_payload(payload))
        if not jobs:
            return None
        return max(jobs, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""))

    def _run_job(self, job_id: str, payload: dict[str, Any]) -> None:
        self._update(job_id, status="running", progress_step=0, progress_total=1, progress_pct=0.0, progress_label="开始训练", progress_details=[], started_at=datetime.now(UTC).isoformat())

        def progress(step: int, total: int, label: str, details: list[str] | None = None) -> None:
            pct = round((step / max(total, 1)) * 100, 2)
            self._update(job_id, progress_step=step, progress_total=total, progress_pct=pct, progress_label=label, progress_details=details or [])

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
                progress_details=["模型产物已保存", "模型列表已刷新"],
                finished_at=datetime.now(UTC).isoformat(),
                model_id=model.get("model_id"),
                model=model,
                error=None,
            )
        except Exception as error:
            error_message = self._normalize_error_message(str(error))
            progress_details = getattr(error, "progress_details", None)
            if isinstance(progress_details, list) and progress_details:
                normalized_details = [self._normalize_error_message(str(detail)) for detail in progress_details]
            else:
                normalized_details = [error_message]
            self._update(
                job_id,
                status="failed",
                progress_pct=100.0,
                progress_label="训练失败",
                progress_details=normalized_details,
                finished_at=datetime.now(UTC).isoformat(),
                error=error_message,
            )

    def _update(self, job_id: str, **updates: Any) -> None:
        current = self.get(job_id) or {"job_id": job_id}
        current.update(updates)
        current["updated_at"] = datetime.now(UTC).isoformat()
        self._write_status(current)

    def _write_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            path = self._path(str(payload["job_id"]))
            temp_path = path.with_suffix(f"{path.suffix}.tmp")
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temp_path.replace(path)

    def _path(self, job_id: str) -> Path:
        safe_job_id = "".join(ch for ch in job_id if ch.isalnum() or ch in {"-", "_"})
        return self.root / f"{safe_job_id}.json"

    @classmethod
    def _normalize_job_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if isinstance(normalized.get("error"), str):
            normalized["error"] = cls._normalize_error_message(str(normalized["error"]))
        details = normalized.get("progress_details")
        if isinstance(details, list):
            normalized["progress_details"] = [cls._normalize_error_message(str(detail)) for detail in details]
        return normalized

    @staticmethod
    def _normalize_error_message(message: str) -> str:
        if message == "PPO training requires at least one symbol with two daily bars":
            return "no symbols have enough daily bars after train/validation split; please widen the training date range or lower min_validation_bars"
        return message


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
