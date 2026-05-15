from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.trading_calendar import is_opening_buy_window, market_now, market_trade_date, previous_trading_day
from app.market.data_service import MarketDataService
from app.models.event_log import EventLogType
from app.market.providers.base import DailyBarSnapshot, IntradayBarSnapshot
from app.models.account import Account
from app.models.order import Order, OrderSide, OrderStatus
from app.models.position import Position
from app.models.smart_selection_item import SmartSelectionItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus
from app.models.strategy import Strategy, StrategyExecutionMode, StrategyStatus, StrategyTargetType, StrategyType
from app.models.strategy_run import StrategyRun, StrategyRunStatus
from app.models.strategy_version import StrategyVersion
from app.market.security_names import security_display
from app.models.strategy_run_item import StrategyRunItem
from app.models.watchlist import WatchlistItem
from app.schemas.strategy import (
    StrategyCompareRead,
    StrategyCompareRequest,
    StrategyCompareItemRead,
    StrategyCreate,
    StrategyDeleteRead,
    StrategyParameterDiffRead,
    StrategyRead,
    StrategyRunItemRead,
    StrategyRunRead,
    StrategyTemplateRead,
    StrategyUpdate,
    StrategyVersionRead,
)
from app.reporting.event_log_service import EventLogService
from app.strategy.dto import StrategyRunReadBuilder, as_utc_datetime
from app.strategy.contracts import StrategySignal
from app.strategy.plugins import StrategyPluginRegistry
from app.strategy.targets import StrategyTargetResolver, recommendation_snapshot_datetime
from app.trading.reason_codes import normalize_reason_code
from app.trading.service import TradingService

STRATEGY_READINESS_DRAFT = "draft"
STRATEGY_READINESS_OBSERVING = "observing"
STRATEGY_READINESS_PAPER_VERIFIED = "paper_verified"
STRATEGY_READINESS_PAUSED = "paused"
STRATEGY_EXECUTION_ENVIRONMENT = "paper"

RECOMMENDATION_ALLOWED_TIMINGS = {"BUY", "STRONG BUY"}
MIN_RECOMMENDATION_SCORE = 60.0
PRICE_QUANTUM = Decimal("0.0001")

INTRADAY_TIMING_DEFAULTS = {
    "intraday_timing_enabled": True,
    "intraday_interval": "5m",
    "intraday_vwap_confirm": True,
    "intraday_volume_ratio_min": 1.2,
    "intraday_pullback_max_pct": 0.025,
    "intraday_stop_loss_enabled": True,
}

TEMPLATE_CATEGORY_LABELS = {
    "breakout": "突破",
    "mean_reversion": "均值回归",
    "momentum": "动量",
    "grid": "网格",
    "factor_scoring": "因子打分",
    "portfolio_rebalance": "组合再平衡",
}

@dataclass(slots=True)
class ExecutionPlan:
    side: str | None
    quantity: int
    price: float | None
    reason: str | None
    execution_blockers: list[str]
    recommendation_confirmed: bool | None = None
    confirmation_source: str | None = None
    recommendation_score: float | None = None
    recommendation_timing: str | None = None
    recommendation_snapshot_date: str | None = None
    position_add_path: str | None = None
    position_pct: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None


@dataclass(slots=True)
class RecommendationSnapshotContext:
    item: SmartSelectionItem | None
    snapshot_date: date | None
    snapshot_expired: bool = False


class StrategyService:
    def __init__(self) -> None:
        self.plugin_registry = StrategyPluginRegistry()
        self.plugins = self.plugin_registry.plugins
        self.target_resolver = StrategyTargetResolver()
        self.run_read_builder = StrategyRunReadBuilder(
            as_str=self._as_str,
            as_int=self._as_int,
            as_float=self._as_float,
            as_bool=self._as_bool,
            as_str_list=self._as_str_list,
        )
        self.market_data_service = MarketDataService()
        self.history_service = self.market_data_service
        self.trading_service = TradingService()
        self.event_log_service = EventLogService()

    def list_strategies(self, db: Session, tenant_id: str = settings.default_tenant_id, user_id: int | None = None) -> list[StrategyRead]:
        strategies = db.scalars(
            select(Strategy)
            .where(
                Strategy.tenant_id == tenant_id,
                Strategy.user_id == user_id,
            )
            .order_by(Strategy.created_at.asc(), Strategy.id.asc())
        ).all()
        return [self._build_strategy_read(db, strategy) for strategy in strategies if not self._is_deleted(strategy)]

    def get_latest_run(
        self,
        db: Session,
        *,
        strategy_id: int | None = None,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> StrategyRunRead | None:
        query = (
            select(StrategyRun)
            .where(StrategyRun.tenant_id == tenant_id, StrategyRun.user_id == user_id)
            .order_by(StrategyRun.created_at.desc(), StrategyRun.id.desc())
            .limit(1)
        )
        if strategy_id is not None:
            query = query.where(StrategyRun.strategy_id == strategy_id)

        run = db.scalar(query)
        if run is None:
            return None
        return self._build_run_read(db, run)

    def list_run_history(
        self,
        db: Session,
        *,
        limit: int = 10,
        strategy_id: int | None = None,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> list[StrategyRunRead]:
        query = (
            select(StrategyRun)
            .where(StrategyRun.tenant_id == tenant_id, StrategyRun.user_id == user_id)
            .order_by(StrategyRun.created_at.desc(), StrategyRun.id.desc())
            .limit(limit)
        )
        if strategy_id is not None:
            query = query.where(StrategyRun.strategy_id == strategy_id)

        runs = db.scalars(query).all()
        return [self._build_run_read(db, run) for run in runs]

    def create_strategy(
        self,
        db: Session,
        payload: StrategyCreate,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> StrategyRead:
        strategy_type = self._parse_strategy_type(payload.strategy_type)
        self._validate_strategy_parameters(strategy_type, payload.parameters, user_id=user_id)
        normalized_parameters = self._normalize_strategy_parameters(strategy_type, payload.parameters, user_id=user_id)
        target_type, target_config, symbol = self._normalize_target_payload(
            payload.symbol,
            payload.target_type,
            payload.target_config,
        )
        strategy = Strategy(
            tenant_id=tenant_id,
            user_id=user_id,
            name=payload.name.strip(),
            symbol=symbol,
            target_type=target_type,
            target_config=target_config,
            strategy_type=strategy_type,
            status=StrategyStatus.DRAFT,
            execution_mode=self._parse_execution_mode(payload.execution_mode),
            parameters=normalized_parameters,
        )
        db.add(strategy)
        db.commit()
        db.refresh(strategy)
        self._record_strategy_version(db, strategy)
        return self._build_strategy_read(db, strategy)

    def update_strategy(
        self,
        db: Session,
        strategy_id: int,
        payload: StrategyUpdate,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> StrategyRead:
        strategy = self._get_strategy(db, strategy_id, tenant_id, user_id)

        if payload.name is not None:
            strategy.name = payload.name.strip()
        if payload.strategy_type is not None:
            strategy.strategy_type = self._parse_strategy_type(payload.strategy_type)
            self._validate_strategy_parameters(strategy.strategy_type, strategy.parameters, user_id=user_id)
            strategy.parameters = self._normalize_strategy_parameters(strategy.strategy_type, strategy.parameters, user_id=user_id)
        if payload.status is not None:
            strategy.status = self._parse_strategy_status(payload.status)
        if payload.execution_mode is not None:
            strategy.execution_mode = self._parse_execution_mode(payload.execution_mode)
        if payload.parameters is not None:
            self._validate_strategy_parameters(strategy.strategy_type, payload.parameters, user_id=user_id)
            strategy.parameters = self._normalize_strategy_parameters(strategy.strategy_type, payload.parameters, user_id=user_id)
        if payload.symbol is not None or payload.target_type is not None or payload.target_config is not None:
            target_type, target_config, symbol = self._normalize_target_payload(
                payload.symbol if payload.symbol is not None else strategy.symbol,
                payload.target_type if payload.target_type is not None else strategy.target_type.value,
                payload.target_config if payload.target_config is not None else strategy.target_config,
            )
            strategy.target_type = target_type
            strategy.target_config = target_config
            strategy.symbol = symbol

        db.commit()
        db.refresh(strategy)
        self._record_strategy_version(db, strategy)
        return self._build_strategy_read(db, strategy)

    def list_strategy_versions(
        self,
        db: Session,
        strategy_id: int,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> list[StrategyVersionRead]:
        self._get_strategy(db, strategy_id, tenant_id, user_id)
        versions = db.scalars(
            select(StrategyVersion)
            .where(
                StrategyVersion.strategy_id == strategy_id,
                StrategyVersion.tenant_id == tenant_id,
                StrategyVersion.user_id == user_id,
            )
            .order_by(StrategyVersion.version.asc(), StrategyVersion.id.asc())
        ).all()
        return [StrategyVersionRead.model_validate(version) for version in versions]

    def list_templates(self) -> list[StrategyTemplateRead]:
        return [StrategyTemplateRead(**template) for template in self._template_catalog()]

    def compare_strategies(
        self,
        db: Session,
        payload: StrategyCompareRequest,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> StrategyCompareRead:
        items = [self._build_compare_item(db, item.strategy_id, item.version_id, tenant_id, user_id) for item in payload.items]
        parameter_diffs = self._build_parameter_diffs(items)
        return StrategyCompareRead(items=items, parameter_diffs=parameter_diffs)

    def delete_strategy(
        self,
        db: Session,
        strategy_id: int,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> StrategyDeleteRead:
        strategy = self._get_strategy(db, strategy_id, tenant_id, user_id)
        parameters = dict(strategy.parameters or {})
        parameters["deleted_at"] = datetime.now(UTC).isoformat()
        strategy.parameters = parameters
        strategy.status = StrategyStatus.PAUSED
        db.commit()
        return StrategyDeleteRead(status="deleted", id=strategy.id)

    def run_strategy(
        self,
        db: Session,
        strategy_id: int,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> StrategyRunRead:
        strategy = self._get_strategy(db, strategy_id, tenant_id, user_id)
        run = StrategyRun(
            tenant_id=tenant_id,
            user_id=user_id,
            strategy_id=strategy.id,
            status=StrategyRunStatus.PENDING,
            signal={},
        )
        db.add(run)
        db.flush()

        try:
            signals: list[dict[str, Any]] = []
            symbols = self._resolve_target_symbols(db, strategy)
            if not symbols:
                run.status = StrategyRunStatus.SUCCESS
                run.signal = self._build_no_target_signal(strategy)
            else:
                for symbol in symbols:
                    signal = self._run_strategy_for_symbol(db, strategy, symbol, run.id)
                    self._record_strategy_signal_event(db, strategy=strategy, run=run, symbol=symbol, signal=signal)
                    db.add(
                        StrategyRunItem(
                            run_id=run.id,
                            symbol=symbol,
                            signal=signal,
                        )
                    )
                    signals.append(signal)
                db.flush()
                run.status = (
                    StrategyRunStatus.FAILED
                    if signals and all("strategy_run_failed" in self._as_str_list(item.get("execution_blockers")) for item in signals)
                    else StrategyRunStatus.SUCCESS
                )
                run.signal = self._aggregate_run_signal(strategy, signals)
        except Exception as exc:
            run.status = StrategyRunStatus.FAILED
            run.signal = self._base_hold_signal(
                symbol=self._strategy_primary_symbol(strategy),
                strategy_name=strategy.strategy_type.value,
                trigger_reason="strategy_run_failed",
                entry_price_ref=None,
                parameters=self._runtime_strategy_parameters(strategy),
            )
            run.signal.update(
                {
                    "execution_mode": strategy.execution_mode.value,
                    "reason": "strategy_run_failed",
                    "error": str(exc),
                    "execution_blockers": ["strategy_run_failed"],
                }
            )

        db.commit()
        db.refresh(run)
        return self._build_run_read(db, run)

    def run_active_strategies(
        self,
        db: Session,
        *,
        strategy_ids: list[int] | None = None,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> list[StrategyRunRead]:
        query = (
            select(Strategy)
            .where(
                Strategy.tenant_id == tenant_id,
                Strategy.user_id == user_id,
                Strategy.status == StrategyStatus.ACTIVE,
            )
            .order_by(Strategy.created_at.asc(), Strategy.id.asc())
        )
        if strategy_ids is not None:
            if not strategy_ids:
                return []
            query = query.where(Strategy.id.in_(strategy_ids))

        strategies = db.scalars(query).all()
        return [self.run_strategy(db, strategy.id, tenant_id, user_id) for strategy in strategies]

    def _build_strategy_read(self, db: Session, strategy: Strategy) -> StrategyRead:
        resolved_symbols = self._resolve_target_symbols(db, strategy)
        signal_symbol = self._strategy_target_label(strategy, resolved_symbols)
        latest_run = db.scalar(
            select(StrategyRun)
            .where(StrategyRun.strategy_id == strategy.id)
            .order_by(StrategyRun.created_at.desc(), StrategyRun.id.desc())
            .limit(1)
        )
        strategy_runs = db.scalars(select(StrategyRun).where(StrategyRun.strategy_id == strategy.id)).all()
        today = market_trade_date()
        run_count_today = sum(1 for item in strategy_runs if self._db_datetime_trade_date(item.created_at) == today)
        total_run_count = len(strategy_runs)

        latest_signal = "hold"
        latest_signal_summary = None
        latest_run_status = None
        latest_run_at = None
        if latest_run is not None:
            latest_run_status = latest_run.status.value
            latest_run_at = self._as_utc_datetime(latest_run.created_at)
            latest_signal = str((latest_run.signal or {}).get("signal", "hold"))
            latest_signal_summary = self._build_signal_summary(latest_run.signal or {})

        readiness_status, readiness_summary = self._current_strategy_readiness(db, strategy)

        return StrategyRead(
            id=strategy.id,
            tenant_id=strategy.tenant_id,
            name=strategy.name,
            symbol=strategy.symbol,
            target_type=strategy.target_type.value,
            target_config=self._strategy_target_config(strategy),
            strategy_type=strategy.strategy_type.value,
            status=strategy.status.value,
            execution_mode=strategy.execution_mode.value,
            parameters=strategy.parameters,
            latest_signal=latest_signal,
            latest_signal_summary=latest_signal_summary,
            readiness_status=readiness_status,
            readiness_summary=readiness_summary,
            signal_symbol=signal_symbol,
            signal_symbol_display=self._strategy_target_display_label(strategy, resolved_symbols, signal_symbol),
            resolved_target_count=len(resolved_symbols),
            latest_run_status=latest_run_status,
            latest_run_at=latest_run_at,
            run_count_today=int(run_count_today),
            total_run_count=int(total_run_count),
            strategy_metadata=self._strategy_metadata_payload(strategy, resolved_symbols=resolved_symbols),
        )

    def _strategy_target_display_label(
        self,
        strategy: Strategy,
        resolved_symbols: list[str],
        fallback_label: str,
    ) -> str:
        if strategy.target_type == StrategyTargetType.SINGLE_SYMBOL:
            symbol = self.target_resolver.primary_symbol(strategy)
            return security_display(symbol) if symbol else fallback_label
        if strategy.target_type == StrategyTargetType.SPECIAL_ATTENTION:
            if not resolved_symbols:
                return fallback_label
            first_label = security_display(resolved_symbols[0])
            if len(resolved_symbols) == 1:
                return first_label
            return f"{first_label} 等 {len(resolved_symbols)} 只"
        return fallback_label

    def _evaluate_strategy(self, strategy: Strategy, symbol: str) -> dict[str, Any]:
        plugin = self.plugin_registry.get(strategy.strategy_type.value)

        history_limit = self._required_history_limit(strategy)
        bars = sorted(
            self._load_price_bars(symbol, history_limit),
            key=lambda item: item.trade_date,
        )
        if not bars:
            return self._base_hold_signal(
                symbol=symbol,
                strategy_name=strategy.strategy_type.value,
                trigger_reason="history_unavailable",
                entry_price_ref=None,
                parameters=self._runtime_strategy_parameters(strategy),
            )

        parameters = self._runtime_strategy_parameters(strategy)
        context = plugin.build_context(
            execution_mode=strategy.execution_mode.value,
            parameters=parameters,
            history_available=len(bars),
            environment=STRATEGY_EXECUTION_ENVIRONMENT,
        )
        return self._normalize_signal(
            symbol=symbol,
            strategy_name=strategy.strategy_type.value,
            signal=StrategySignal.coerce(plugin.evaluate(symbol, bars, parameters)).to_legacy(),
            parameters=parameters,
            strategy_metadata=self._plugin_metadata(plugin, parameters),
            strategy_context=context.to_dict(),
        )

    def _runtime_strategy_parameters(self, strategy: Strategy) -> dict[str, Any]:
        parameters = dict(strategy.parameters or {})
        if strategy.strategy_type == StrategyType.RL_TRADING and parameters.get("rl_policy_mode") == "trained_model" and strategy.user_id is not None:
            parameters["model_registry_root"] = self._rl_model_registry_root(strategy.user_id)
        return parameters

    def _build_execution_signal(self, db: Session, strategy: Strategy, signal: dict[str, Any], *, symbol: str, strategy_run_id: int | None) -> dict[str, Any]:
        correlation_id = str(uuid4())
        signal_payload = {
            **signal,
            "execution_mode": strategy.execution_mode.value,
            "execution_environment": STRATEGY_EXECUTION_ENVIRONMENT,
            "order_submitted": False,
            "order_id": None,
            "order_status": None,
            "side": None,
            "quantity": None,
            "price": None,
            "reason": None,
            "recommendation_confirmed": signal.get("recommendation_confirmed"),
            "confirmation_source": signal.get("confirmation_source"),
            "recommendation_snapshot_date": signal.get("recommendation_snapshot_date"),
            "position_add_path": signal.get("position_add_path"),
            "execution_blockers": list(signal.get("execution_blockers", [])),
            "correlation_id": correlation_id,
        }

        if strategy.execution_mode == StrategyExecutionMode.SIGNAL_ONLY:
            signal_payload["reason"] = "signal_only_mode"
            signal_payload["execution_blockers"] = ["signal_only_mode"]
            return signal_payload

        readiness_status, readiness_summary = self._current_strategy_readiness(db, strategy)
        signal_payload["strategy_readiness_status"] = readiness_status
        signal_payload["strategy_readiness_summary"] = readiness_summary

        raw_signal = str(signal_payload.get("signal", "hold"))
        if raw_signal == "hold":
            self._sync_position_exit_guard_from_signal(db, symbol, signal_payload, signal_type=raw_signal, user_id=strategy.user_id)
            signal_payload["reason"] = "signal_hold"
            return signal_payload

        self._apply_intraday_timing_gate(strategy, signal_payload, symbol=symbol, raw_signal=raw_signal)
        raw_signal = str(signal_payload.get("signal", "hold"))
        if raw_signal == "hold":
            self._sync_position_exit_guard_from_signal(db, symbol, signal_payload, signal_type=raw_signal, user_id=strategy.user_id)
            signal_payload["reason"] = "intraday_timing_blocked"
            return signal_payload

        plan = (
            self._build_open_execution_plan(db, strategy, signal_payload, symbol=symbol)
            if raw_signal == "buy"
            else self._build_exit_execution_plan(db, strategy, signal_payload, symbol=symbol)
        )

        signal_payload.update(
            {
                "side": plan.side,
                "quantity": plan.quantity or None,
                "price": plan.price,
                "reason": plan.reason,
                "recommendation_confirmed": plan.recommendation_confirmed,
                "confirmation_source": plan.confirmation_source,
                "recommendation_snapshot_date": plan.recommendation_snapshot_date,
                "position_add_path": plan.position_add_path,
                "execution_blockers": plan.execution_blockers,
                "recommendation_score": plan.recommendation_score,
                "recommendation_timing": plan.recommendation_timing,
                "position_pct": plan.position_pct if plan.position_pct is not None else signal_payload.get("position_pct"),
                "stop_loss_price": plan.stop_loss_price if plan.stop_loss_price is not None else signal_payload.get("stop_loss_price"),
                "take_profit_price": plan.take_profit_price if plan.take_profit_price is not None else signal_payload.get("take_profit_price"),
            }
        )
        self._sync_position_exit_guard_from_signal(db, symbol, signal_payload, signal_type=raw_signal, user_id=strategy.user_id)

        if plan.execution_blockers:
            signal_payload["reason"] = plan.reason or plan.execution_blockers[0]
            return signal_payload

        order_result = self.trading_service.place_order(
            db,
            symbol=symbol,
            side=plan.side or "buy",
            order_type="market",
            quantity=plan.quantity,
            price=plan.price or float(signal_payload.get("entry_price_ref") or 0.0),
            note_prefix=f"strategy {strategy.id} {signal_payload.get('trigger_reason', raw_signal)}",
            stop_loss_price=signal_payload.get("stop_loss_price") if plan.side == "buy" else None,
            take_profit_price=signal_payload.get("take_profit_price") if plan.side == "buy" else None,
            strategy_add_increment=plan.position_add_path == "first_add",
            user_id=strategy.user_id,
            correlation_id=correlation_id,
            strategy_id=strategy.id,
            strategy_run_id=strategy_run_id,
        )
        order_payload = order_result.get("order", {})
        normalized_reason = self._map_rejection_reason(
            order_result.get("rejection_reason") or order_payload.get("reject_reason") or order_result.get("status")
        )
        order_status = self._as_str(order_payload.get("status"))
        accepted = bool(order_result.get("status") == "accepted" and order_status != "rejected")

        signal_payload["order_submitted"] = accepted
        signal_payload["order_id"] = self._as_int(order_payload.get("id"))
        signal_payload["order_status"] = order_status
        signal_payload["reason"] = "order_submitted" if accepted else normalized_reason
        signal_payload["quantity"] = self._as_int(order_payload.get("quantity")) or plan.quantity
        signal_payload["price"] = self._as_float(order_payload.get("price")) or plan.price
        if not accepted and normalized_reason is not None:
            signal_payload["execution_blockers"] = [normalized_reason]

        return signal_payload

    def _record_strategy_signal_event(self, db: Session, *, strategy: Strategy, run: StrategyRun, symbol: str, signal: dict[str, Any]) -> None:
        self.event_log_service.append(
            db,
            tenant_id=strategy.tenant_id,
            user_id=strategy.user_id,
            event_type=EventLogType.STRATEGY_SIGNAL,
            symbol=symbol,
            strategy_id=strategy.id,
            strategy_run_id=run.id,
            correlation_id=str(signal.get("correlation_id") or uuid4()),
            payload={
                "signal": signal.get("signal"),
                "order_submitted": signal.get("order_submitted"),
                "execution_blockers": signal.get("execution_blockers", []),
                "target_position_pct": signal.get("position_pct"),
                "trigger_reason": signal.get("trigger_reason"),
                "reason": signal.get("reason"),
            },
        )

    def _build_run_read(self, db: Session, run: StrategyRun) -> StrategyRunRead:
        return self.run_read_builder.build_run_read(db, run)

    def _build_run_item_read(self, item: StrategyRunItem) -> StrategyRunItemRead:
        return self.run_read_builder.build_run_item_read(item)

    def _record_strategy_version(self, db: Session, strategy: Strategy) -> None:
        latest_version = db.scalar(select(func.max(StrategyVersion.version)).where(StrategyVersion.strategy_id == strategy.id))
        version = StrategyVersion(
            tenant_id=strategy.tenant_id,
            user_id=strategy.user_id,
            strategy_id=strategy.id,
            version=int(latest_version or 0) + 1,
            name=strategy.name,
            symbol=strategy.symbol,
            strategy_type=strategy.strategy_type.value,
            execution_mode=strategy.execution_mode.value,
            target_type=strategy.target_type.value,
            target_config=self._strategy_target_config(strategy),
            parameters=dict(strategy.parameters or {}),
        )
        db.add(version)
        db.commit()

    def _build_compare_item(
        self,
        db: Session,
        strategy_id: int,
        version_id: int | None,
        tenant_id: str,
        user_id: int | None,
    ) -> StrategyCompareItemRead:
        strategy = self._get_strategy(db, strategy_id, tenant_id, user_id)
        version = None
        if version_id is not None:
            version = db.scalar(
                select(StrategyVersion).where(
                    StrategyVersion.id == version_id,
                    StrategyVersion.strategy_id == strategy_id,
                    StrategyVersion.tenant_id == tenant_id,
                    StrategyVersion.user_id == user_id,
                )
            )
            if version is None:
                raise HTTPException(status_code=404, detail="strategy version not found")

        latest_run = db.scalar(
            select(StrategyRun).where(StrategyRun.strategy_id == strategy_id).order_by(StrategyRun.created_at.desc(), StrategyRun.id.desc()).limit(1)
        )
        latest_run_summary = None
        if latest_run is not None:
            signal = latest_run.signal or {}
            latest_run_summary = {
                "id": latest_run.id,
                "status": latest_run.status.value,
                "created_at": self._as_utc_datetime(latest_run.created_at).isoformat(),
                "signal": signal.get("signal", "hold"),
                "summary": self._build_signal_summary(signal),
            }

        if version is not None:
            return StrategyCompareItemRead(
                key=f"strategy:{strategy_id}:version:{version.id}",
                strategy_id=strategy_id,
                version_id=version.id,
                version=version.version,
                name=version.name,
                symbol=version.symbol,
                strategy_type=version.strategy_type,
                execution_mode=version.execution_mode,
                target_type=version.target_type,
                target_config=version.target_config or {},
                parameters=version.parameters or {},
                latest_run=latest_run_summary,
                backtest_summary=self._latest_backtest_summary(strategy_id),
                created_at=self._as_utc_datetime(version.created_at),
            )

        return StrategyCompareItemRead(
            key=f"strategy:{strategy_id}:current",
            strategy_id=strategy_id,
            version_id=None,
            version=None,
            name=strategy.name,
            symbol=strategy.symbol,
            strategy_type=strategy.strategy_type.value,
            execution_mode=strategy.execution_mode.value,
            target_type=strategy.target_type.value,
            target_config=self._strategy_target_config(strategy),
            parameters=dict(strategy.parameters or {}),
            latest_run=latest_run_summary,
            backtest_summary=self._latest_backtest_summary(strategy_id),
            created_at=self._as_utc_datetime(strategy.updated_at),
        )

    @staticmethod
    def _build_parameter_diffs(items: list[StrategyCompareItemRead]) -> list[StrategyParameterDiffRead]:
        keys = sorted({key for item in items for key in item.parameters.keys()})
        diffs: list[StrategyParameterDiffRead] = []
        for key in keys:
            values = {item.key: item.parameters.get(key) for item in items}
            if len({repr(value) for value in values.values()}) > 1:
                diffs.append(StrategyParameterDiffRead(key=key, values=values))
        return diffs

    @staticmethod
    def _latest_backtest_summary(strategy_id: int) -> dict[str, Any]:
        jobs_dir = Path(__file__).resolve().parents[3] / "artifacts" / "backtest_jobs"
        summaries: list[dict[str, Any]] = []
        for path in jobs_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            result = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(result, dict) or result.get("strategy_id") != strategy_id:
                continue
            summaries.append(
                {
                    "job_id": payload.get("job_id"),
                    "updated_at": payload.get("updated_at"),
                    "status": result.get("status"),
                    "symbol": result.get("symbol"),
                    "total_return_pct": result.get("total_return_pct"),
                    "max_drawdown_pct": result.get("max_drawdown_pct"),
                    "trade_count": result.get("trade_count"),
                    "bars": result.get("bars"),
                }
            )
        if not summaries:
            return {}
        return sorted(summaries, key=lambda item: str(item.get("updated_at") or ""), reverse=True)[0]

    @staticmethod
    def _as_utc_datetime(value: datetime) -> datetime:
        return as_utc_datetime(value)

    def _run_strategy_for_symbol(self, db: Session, strategy: Strategy, symbol: str, strategy_run_id: int | None = None) -> dict[str, Any]:
        try:
            signal = self._evaluate_strategy(strategy, symbol)
            return self._build_execution_signal(db, strategy, signal, symbol=symbol, strategy_run_id=strategy_run_id)
        except Exception as exc:
            payload = self._base_hold_signal(
                symbol=symbol,
                strategy_name=strategy.strategy_type.value,
                trigger_reason="strategy_run_failed",
                entry_price_ref=None,
                parameters=self._runtime_strategy_parameters(strategy),
            )
            payload.update(
                {
                    "execution_mode": strategy.execution_mode.value,
                    "reason": "strategy_run_failed",
                    "error": str(exc),
                    "execution_blockers": ["strategy_run_failed"],
                }
            )
            return payload

    def _aggregate_run_signal(self, strategy: Strategy, signals: list[dict[str, Any]]) -> dict[str, Any]:
        if not signals:
            return self._build_no_target_signal(strategy)
        primary = next((item for item in signals if item.get("order_submitted")), None)
        if primary is None:
            primary = next((item for item in signals if item.get("signal") != "hold"), None)
        if primary is None:
            primary = signals[0]
        payload = {**primary}
        payload["target_type"] = strategy.target_type.value
        payload["target_config"] = self._strategy_target_config(strategy)
        payload["resolved_symbol_count"] = len(signals)
        payload["resolved_symbols"] = [str(item.get("symbol")) for item in signals if item.get("symbol")]
        payload["strategy_metadata"] = self._strategy_metadata_payload(strategy, resolved_symbols=payload["resolved_symbols"])
        return payload

    def _build_no_target_signal(self, strategy: Strategy) -> dict[str, Any]:
        payload = self._base_hold_signal(
            symbol=self._strategy_primary_symbol(strategy),
            strategy_name=strategy.strategy_type.value,
            trigger_reason="no_target_symbols",
            entry_price_ref=None,
            parameters=self._runtime_strategy_parameters(strategy),
        )
        payload.update(
            {
                "execution_mode": strategy.execution_mode.value,
                "reason": "no_target_symbols",
                "execution_blockers": ["no_target_symbols"],
                "target_type": strategy.target_type.value,
                "target_config": self._strategy_target_config(strategy),
                "resolved_symbol_count": 0,
                "resolved_symbols": [],
                "strategy_metadata": self._strategy_metadata_payload(strategy, resolved_symbols=[]),
            }
        )
        return payload

    def _apply_intraday_timing_gate(self, strategy: Strategy, signal: dict[str, Any], *, symbol: str, raw_signal: str) -> None:
        if raw_signal not in {"buy", "sell", "reduce"}:
            return
        if not self._strategy_bool_parameter(strategy, "intraday_timing_enabled"):
            signal.update(
                {
                    "intraday_timing_status": "disabled",
                    "intraday_trigger_reason": "disabled",
                    "intraday_vwap": None,
                    "intraday_volume_ratio": None,
                    "intraday_latest_close": None,
                }
            )
            return

        interval = self._strategy_str_parameter(strategy, "intraday_interval") or "5m"
        try:
            bars = self.market_data_service.get_intraday_bars(symbol, interval=interval, limit=120)
        except Exception:
            bars = []
        bars = self._filter_current_intraday_bars(bars, now=self._current_market_datetime())
        if not bars:
            signal.update(
                {
                    "intraday_timing_status": "unavailable",
                    "intraday_trigger_reason": "intraday_data_unavailable",
                    "intraday_vwap": None,
                    "intraday_volume_ratio": None,
                    "intraday_latest_close": None,
                }
            )
            return

        verdict = self._evaluate_intraday_timing(strategy, signal, bars, raw_signal=raw_signal)
        signal.update(verdict)
        if verdict["intraday_timing_status"] == "blocked":
            signal["signal"] = "hold"
            blockers = self._as_str_list(signal.get("execution_blockers"))
            blockers.append(str(verdict["intraday_trigger_reason"]))
            signal["execution_blockers"] = list(dict.fromkeys(blockers))

    def _evaluate_intraday_timing(
        self,
        strategy: Strategy,
        signal: dict[str, Any],
        bars: list[IntradayBarSnapshot],
        *,
        raw_signal: str,
    ) -> dict[str, Any]:
        latest = bars[-1]
        latest_close = latest.close_price
        vwap = self._intraday_vwap(bars)
        volume_ratio = self._intraday_volume_ratio(bars)
        session_high = max(bar.high_price for bar in bars)
        recent_lows = [bar.low_price for bar in bars[-5:]]
        recent_low = min(recent_lows) if recent_lows else latest.low_price
        trigger_reason = "intraday_confirmed"
        status = "confirmed"

        if raw_signal == "buy":
            blockers: list[str] = []
            if self._strategy_bool_parameter(strategy, "intraday_vwap_confirm") and vwap is not None and latest_close < vwap:
                blockers.append("intraday_below_vwap")
            if self._recent_intraday_weakness(bars):
                blockers.append("intraday_recent_weakness")
            min_volume_ratio = self._strategy_float_parameter(strategy, "intraday_volume_ratio_min")
            if volume_ratio is not None and volume_ratio < min_volume_ratio:
                blockers.append("intraday_volume_not_confirmed")
            pullback_max_pct = self._strategy_float_parameter(strategy, "intraday_pullback_max_pct")
            if session_high > 0 and (session_high - latest_close) / session_high > pullback_max_pct:
                blockers.append("intraday_pullback_too_deep")
            status = "blocked" if blockers else "confirmed"
            trigger_reason = blockers[0] if blockers else "intraday_buy_confirmed"
        else:
            stop_loss = self._as_float(signal.get("stop_loss_price"))
            take_profit = self._as_float(signal.get("take_profit_price"))
            stop_enabled = self._strategy_bool_parameter(strategy, "intraday_stop_loss_enabled")
            if stop_enabled and stop_loss is not None and latest_close <= stop_loss:
                trigger_reason = "intraday_stop_loss_triggered"
            elif stop_enabled and take_profit is not None and latest_close >= take_profit:
                trigger_reason = "intraday_take_profit_triggered"
            elif vwap is not None and latest_close < vwap:
                trigger_reason = "intraday_below_vwap"
            elif latest_close <= recent_low:
                trigger_reason = "intraday_break_recent_low"
            else:
                status = "blocked"
                trigger_reason = "intraday_exit_not_confirmed"

        return {
            "intraday_timing_status": status,
            "intraday_trigger_reason": trigger_reason,
            "intraday_vwap": round(vwap, 4) if vwap is not None else None,
            "intraday_volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
            "intraday_latest_close": latest_close,
        }

    @staticmethod
    def _filter_current_intraday_bars(bars: list[IntradayBarSnapshot], *, now: datetime) -> list[IntradayBarSnapshot]:
        trade_day = market_trade_date(now)
        current_bars = [bar for bar in bars if bar.bar_time.date() == trade_day]
        return current_bars

    @staticmethod
    def _intraday_vwap(bars: list[IntradayBarSnapshot]) -> float | None:
        total_volume = sum(max(bar.volume, 0.0) for bar in bars)
        if total_volume <= 0:
            return None
        return sum(bar.close_price * max(bar.volume, 0.0) for bar in bars) / total_volume

    @staticmethod
    def _intraday_volume_ratio(bars: list[IntradayBarSnapshot]) -> float | None:
        if len(bars) < 2:
            return None
        previous = [max(bar.volume, 0.0) for bar in bars[:-1]]
        average = sum(previous) / len(previous) if previous else 0.0
        if average <= 0:
            return None
        return max(bars[-1].volume, 0.0) / average

    @staticmethod
    def _recent_intraday_weakness(bars: list[IntradayBarSnapshot]) -> bool:
        if len(bars) < 3:
            return False
        recent = bars[-3:]
        return all(bar.close_price < bar.open_price for bar in recent) and recent[-1].close_price < recent[0].close_price

    def _strategy_bool_parameter(self, strategy: Strategy, key: str) -> bool:
        return bool(strategy.parameters.get(key, INTRADAY_TIMING_DEFAULTS[key]))

    def _strategy_float_parameter(self, strategy: Strategy, key: str) -> float:
        return float(strategy.parameters.get(key, INTRADAY_TIMING_DEFAULTS[key]))

    def _strategy_str_parameter(self, strategy: Strategy, key: str) -> str:
        return str(strategy.parameters.get(key, INTRADAY_TIMING_DEFAULTS[key]))

    def _build_open_execution_plan(self, db: Session, strategy: Strategy, signal: dict[str, Any], *, symbol: str) -> ExecutionPlan:
        blockers: list[str] = []
        position = self._get_position(db, symbol, strategy.user_id)
        position_add_path = self._resolve_position_add_path(position)
        if position_add_path == "blocked_repeat_add":
            blockers.append("blocked_repeat_add")

        recommendation_context = self._resolve_recommendation_snapshot(
            db,
            symbol,
            now=self._current_market_datetime(),
            user_id=strategy.user_id,
        )
        recommendation = recommendation_context.item
        special_attention_confirmed = self._is_special_attention_watchlist_symbol(db, symbol, strategy.user_id)
        position_confirmed = position is not None and position.quantity > 0
        recommendation_score = None
        recommendation_timing = None
        bypass_recommendation_confirmation = bool(strategy.parameters.get("bypass_recommendation_confirmation", False))
        recommendation_confirmed = special_attention_confirmed or position_confirmed or bypass_recommendation_confirmation
        confirmation_source = (
            "special_attention_watchlist"
            if special_attention_confirmed
            else "existing_position"
            if position_confirmed
            else "simulation_bypass"
            if bypass_recommendation_confirmation
            else "none"
        )
        recommendation_snapshot_date = None if (special_attention_confirmed or position_confirmed) else self._serialize_date(recommendation_context.snapshot_date)

        signal_position_pct = self._clamp_fraction(signal.get("position_pct"), default=self._clamp_fraction(strategy.parameters.get("position_pct"), default=0.1))
        stop_loss_price = self._as_float(signal.get("stop_loss_price"))
        take_profit_price = self._as_float(signal.get("take_profit_price"))

        if not special_attention_confirmed and not position_confirmed and not bypass_recommendation_confirmation:
            if recommendation_context.snapshot_expired:
                blockers.append("recommendation_snapshot_expired")
            elif recommendation is None:
                blockers.append("recommendation_missing")
            else:
                recommendation_score = float(recommendation.score)
                recommendation_timing = (
                    str((recommendation.raw_detail or {}).get("timing"))
                    if (recommendation.raw_detail or {}).get("timing") is not None
                    else None
                )
                recommendation_passed = True
                if recommendation_score < MIN_RECOMMENDATION_SCORE:
                    recommendation_passed = False
                if recommendation_timing not in RECOMMENDATION_ALLOWED_TIMINGS:
                    recommendation_passed = False

                if recommendation_passed:
                    recommendation_confirmed = True
                    confirmation_source = "smart_selection"
                    recommendation_position_pct = self._recommendation_position_pct(recommendation)
                    signal_position_pct = min(signal_position_pct, recommendation_position_pct)
                    if recommendation.stop_loss_price is not None:
                        stop_loss_price = max(stop_loss_price or recommendation.stop_loss_price, recommendation.stop_loss_price)
                    if recommendation.target_price is not None:
                        take_profit_price = min(take_profit_price or recommendation.target_price, recommendation.target_price)
                elif recommendation_score < MIN_RECOMMENDATION_SCORE:
                    blockers.append("recommendation_score_below_threshold")
                elif recommendation_timing not in RECOMMENDATION_ALLOWED_TIMINGS:
                    blockers.append("recommendation_timing_not_ready")

        price, quote = self._resolve_execution_price(symbol, signal)
        if position_add_path == "blocked_repeat_add":
            return ExecutionPlan(
                side="buy",
                quantity=0,
                price=price,
                reason="blocked_repeat_add",
                execution_blockers=["blocked_repeat_add"],
                recommendation_confirmed=recommendation_confirmed,
                confirmation_source=confirmation_source,
                recommendation_score=recommendation_score,
                recommendation_timing=recommendation_timing,
                recommendation_snapshot_date=recommendation_snapshot_date,
                position_add_path=position_add_path,
                position_pct=signal_position_pct,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
            )
        if not self._is_opening_trade_window():
            blockers.append("opening_window_closed")
        if bool(quote.get("is_halted", False)):
            blockers.append("symbol_halted")
        if abs(float(quote.get("change_percent", 0.0) or 0.0)) >= 9.5:
            blockers.append("near_limit_move")

        account = self._get_default_account(db, strategy.user_id)
        if account is None:
            blockers.append("account_missing")
            return ExecutionPlan(
                side="buy",
                quantity=0,
                price=price,
                reason=blockers[0],
                execution_blockers=list(dict.fromkeys(blockers)),
                recommendation_confirmed=recommendation_confirmed,
                confirmation_source=confirmation_source,
                recommendation_score=recommendation_score,
                recommendation_timing=recommendation_timing,
                recommendation_snapshot_date=recommendation_snapshot_date,
                position_add_path=position_add_path,
                position_pct=signal_position_pct,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
            )

        current_position_value = float(position.quantity) * price if position is not None else 0.0
        total_position_value = float(db.scalar(self.trading_service._total_position_value_query(account.id)) or Decimal("0"))
        quantity = self._calculate_buy_quantity(
            account=account,
            price=price,
            position_pct=signal_position_pct,
            current_position_value=current_position_value,
            total_position_value=total_position_value,
        )
        if quantity < 100:
            blockers.append("quantity_below_min_lot")

        if not blockers:
            blockers.extend(
                self._preflight_risk_blockers(
                    db,
                    account=account,
                    position=position,
                    side="buy",
                    quantity=quantity,
                    price=price,
                    current_position_value=current_position_value,
                    total_position_value=total_position_value,
                    quote=quote,
                )
            )

        blockers = list(dict.fromkeys(blockers))
        return ExecutionPlan(
            side="buy",
            quantity=quantity,
            price=price,
            reason=blockers[0] if blockers else None,
            execution_blockers=blockers,
            recommendation_confirmed=recommendation_confirmed,
            confirmation_source=confirmation_source,
            recommendation_score=recommendation_score,
            recommendation_timing=recommendation_timing,
            recommendation_snapshot_date=recommendation_snapshot_date,
            position_add_path=position_add_path,
            position_pct=signal_position_pct,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )

    def _build_exit_execution_plan(self, db: Session, strategy: Strategy, signal: dict[str, Any], *, symbol: str) -> ExecutionPlan:
        blockers: list[str] = []
        price, quote = self._resolve_execution_price(symbol, signal)
        account = self._get_default_account(db, strategy.user_id)
        if account is not None:
            self.trading_service.unlock_settled_positions(db, account.id)
        position = self._get_position(db, symbol, strategy.user_id)

        if account is None:
            blockers.append("account_missing")
        if position is None or position.available_quantity < 100:
            blockers.append("insufficient_position")
        if position is not None and self._has_pending_sell_order(db, account_id=position.account_id, symbol=symbol):
            blockers.append("pending_exit_order")

        quantity = 0
        if not blockers and position is not None:
            quantity = self._calculate_sell_quantity(
                available_quantity=position.available_quantity,
                signal_type=str(signal.get("signal", "sell")),
                position_pct=self._clamp_fraction(signal.get("position_pct"), default=0.5),
            )
            if quantity < 100:
                blockers.append("quantity_below_min_lot")

        if not blockers and account is not None and position is not None:
            blockers.extend(
                self._preflight_risk_blockers(
                    db,
                    account=account,
                    position=position,
                    side="sell",
                    quantity=quantity,
                    price=price,
                    current_position_value=float(position.quantity * position.last_price),
                    total_position_value=float(db.scalar(self.trading_service._total_position_value_query(account.id)) or Decimal("0")),
                    quote=quote,
                )
            )

        blockers = list(dict.fromkeys(blockers))
        return ExecutionPlan(
            side="sell",
            quantity=quantity,
            price=price,
            reason=blockers[0] if blockers else None,
            execution_blockers=blockers,
            recommendation_confirmed=None,
            confirmation_source="none",
            recommendation_score=None,
            recommendation_timing=None,
            recommendation_snapshot_date=None,
            position_add_path=None,
            position_pct=self._clamp_fraction(signal.get("position_pct"), default=1.0 if signal.get("signal") == "sell" else 0.5),
            stop_loss_price=self._as_float(signal.get("stop_loss_price")),
            take_profit_price=self._as_float(signal.get("take_profit_price")),
        )

    def _normalize_signal(
        self,
        *,
        symbol: str,
        strategy_name: str,
        signal: dict[str, Any],
        parameters: dict[str, Any],
        strategy_metadata: dict[str, Any],
        strategy_context: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_signal = str(signal.get("signal", "hold")).lower()
        base_position_pct = self._clamp_fraction(parameters.get("position_pct"), default=0.1)
        default_position_pct = {
            "buy": base_position_pct,
            "reduce": 0.5,
            "sell": 1.0,
            "hold": 0.0,
        }.get(normalized_signal, 0.0)

        payload = {
            **signal,
            "symbol": symbol,
            "strategy": strategy_name,
            "signal": normalized_signal,
            "strength": self._normalize_strength(signal.get("strength")),
            "trigger_reason": self._as_str(signal.get("trigger_reason")) or "no_trigger_reason",
            "entry_price_ref": self._as_float(signal.get("entry_price_ref")),
            "stop_loss_price": self._as_float(signal.get("stop_loss_price")),
            "take_profit_price": self._as_float(signal.get("take_profit_price")),
            "position_pct": self._clamp_fraction(signal.get("position_pct"), default=default_position_pct),
            "market_regime": self._as_str(signal.get("market_regime")) or "neutral",
            "requires_recommendation_confirmation": bool(
                signal.get("requires_recommendation_confirmation", normalized_signal == "buy")
            ),
            "recommendation_confirmed": None,
            "confirmation_source": "none",
            "recommendation_snapshot_date": None,
            "position_add_path": None,
            "execution_blockers": [],
            "filter_passed": bool(signal.get("filter_passed", True)),
            "filter_reasons": self._as_str_list(signal.get("filter_reasons")),
            "trend_ok": self._as_bool(signal.get("trend_ok")),
            "volume_ok": self._as_bool(signal.get("volume_ok")),
            "volatility_ok": self._as_bool(signal.get("volatility_ok")),
            "stretch_ok": self._as_bool(signal.get("stretch_ok")),
            "market_regime_bias": self._as_str(signal.get("market_regime_bias")),
            "strategy_metadata": strategy_metadata,
            "strategy_context": strategy_context,
        }
        payload["standard_signal"] = StrategySignal.coerce(payload).to_dict()
        return payload

    def _base_hold_signal(
        self,
        *,
        symbol: str,
        strategy_name: str,
        trigger_reason: str,
        entry_price_ref: float | None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plugin = self.plugin_registry.get(strategy_name)
        runtime_parameters = dict(parameters or {})
        context = plugin.build_context(
            execution_mode="signal_only",
            parameters=runtime_parameters,
            history_available=0,
            environment=STRATEGY_EXECUTION_ENVIRONMENT,
        ).to_dict()
        payload = {
            "symbol": symbol,
            "strategy": strategy_name,
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": trigger_reason,
            "entry_price_ref": entry_price_ref,
            "stop_loss_price": None,
            "take_profit_price": None,
            "position_pct": 0.0,
            "market_regime": "neutral",
            "requires_recommendation_confirmation": False,
            "recommendation_confirmed": None,
            "confirmation_source": "none",
            "recommendation_snapshot_date": None,
            "position_add_path": None,
            "execution_blockers": [],
            "execution_environment": STRATEGY_EXECUTION_ENVIRONMENT,
            "filter_passed": True,
            "filter_reasons": [],
            "trend_ok": None,
            "volume_ok": None,
            "volatility_ok": None,
            "stretch_ok": None,
            "market_regime_bias": None,
            "strategy_metadata": self._plugin_metadata(plugin, runtime_parameters),
            "strategy_context": context,
        }
        payload["standard_signal"] = StrategySignal.coerce(payload).to_dict()
        return payload

    def _build_signal_summary(self, signal: dict[str, Any]) -> str | None:
        if not signal:
            return None
        signal_label = {
            "buy": "买入",
            "sell": "卖出",
            "reduce": "减仓",
            "hold": "观望",
        }.get(str(signal.get("signal", "hold")), "观望")
        strength_label = {
            "strong": "强",
            "normal": "中",
            "weak": "弱",
        }.get(str(signal.get("strength", "normal")), "中")
        reason = str(signal.get("trigger_reason") or "")
        blocker = next(iter(signal.get("execution_blockers", [])), None)
        if blocker:
            return f"{signal_label}/{strength_label} · {reason} · {blocker}"
        filter_reason = next(iter(self._as_str_list(signal.get("filter_reasons"))), None)
        if filter_reason:
            return f"{signal_label}/{strength_label} · {reason} · {filter_reason}"
        return f"{signal_label}/{strength_label} · {reason}" if reason else f"{signal_label}/{strength_label}"

    def _plugin_metadata(self, plugin, parameters: dict[str, Any]) -> dict[str, Any]:
        payload = plugin.metadata.to_dict()
        payload["minimum_history"] = plugin.minimum_history(parameters)
        return payload

    def _strategy_metadata_payload(self, strategy: Strategy, *, resolved_symbols: list[str]) -> dict[str, Any]:
        plugin = self.plugin_registry.get(strategy.strategy_type.value)
        parameters = self._runtime_strategy_parameters(strategy)
        context = plugin.build_context(
            execution_mode=strategy.execution_mode.value,
            parameters=parameters,
            history_available=0,
            environment=STRATEGY_EXECUTION_ENVIRONMENT,
            position_symbols=tuple(resolved_symbols),
        ).to_dict()
        metadata = self._plugin_metadata(plugin, parameters)
        metadata["target_type"] = strategy.target_type.value
        metadata["resolved_symbol_count"] = len(resolved_symbols)
        metadata["resolved_symbols"] = resolved_symbols
        metadata["strategy_context"] = context
        return metadata

    @staticmethod
    def _parameter_bounds(parameter_schema: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            str(item["key"]): {
                "type": item.get("type"),
                "minimum": item.get("minimum"),
                "maximum": item.get("maximum"),
                "default": item.get("default"),
                "enum": list(item.get("enum") or []),
                "description": item.get("description"),
            }
            for item in parameter_schema
        }

    def _template_catalog(self) -> list[dict[str, Any]]:
        moving_average_meta = self._plugin_metadata(self.plugin_registry.get(StrategyType.MOVING_AVERAGE.value), {"short_window": 5, "long_window": 20})
        macd_meta = self._plugin_metadata(self.plugin_registry.get(StrategyType.MACD.value), {"fast_period": 12, "slow_period": 26, "signal_period": 9})
        rsi_meta = self._plugin_metadata(self.plugin_registry.get(StrategyType.RSI_REVERSAL.value), {"rsi_period": 14})
        boll_meta = self._plugin_metadata(self.plugin_registry.get(StrategyType.BOLLINGER_BAND.value), {"boll_period": 20})
        fusion_meta = self._plugin_metadata(self.plugin_registry.get(StrategyType.SIGNAL_FUSION.value), {})
        rl_meta = self._plugin_metadata(self.plugin_registry.get(StrategyType.RL_TRADING.value), {"rl_policy_mode": "baseline"})
        return [
            {
                "key": "breakout_ma_balanced",
                "name": "趋势突破观察",
                "category": "breakout",
                "description": "使用双均线确认突破后的趋势延续，默认仅做纸面信号观察。",
                "scenario": "适合日线趋势较清晰、希望先验证信号稳定性的标的。",
                "fit_for": ["日线趋势清晰", "希望低频验证", "允许先纸面观察"],
                "not_fit_for": ["高频震荡行情", "追求抄底反转", "缺少基础历史数据"],
                "risk_note": str(moving_average_meta["risk_note"]),
                "minimum_history": int(moving_average_meta["minimum_history"]),
                "auto_trade_allowed": bool(moving_average_meta["auto_trade_allowed"]),
                "research_only": False,
                "parameter_bounds": self._parameter_bounds(list(moving_average_meta["parameter_schema"])),
                "payload": {
                    "name": "趋势突破观察",
                    "symbol": "600519.SH",
                    "strategy_type": "moving_average",
                    "execution_mode": "signal_only",
                    "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.1},
                },
            },
            {
                "key": "mean_reversion_boll_rsi",
                "name": "均值回归观察",
                "category": "mean_reversion",
                "description": "组合 RSI 与布林带观察超卖回补和回归信号，不做收益承诺。",
                "scenario": "适合波动中等、以研究反转信号为目的的标的。",
                "fit_for": ["震荡行情研究", "需要可解释指标值", "默认信号观察"],
                "not_fit_for": ["单边趋势突破", "自动交易直连", "极端消息驱动行情"],
                "risk_note": f"{rsi_meta['risk_note']}；{boll_meta['risk_note']}",
                "minimum_history": max(int(rsi_meta["minimum_history"]), int(boll_meta["minimum_history"])),
                "auto_trade_allowed": False,
                "research_only": False,
                "parameter_bounds": {
                    **self._parameter_bounds(list(rsi_meta["parameter_schema"])),
                    **self._parameter_bounds(list(boll_meta["parameter_schema"])),
                },
                "payload": {
                    "name": "均值回归观察",
                    "symbol": "600519.SH",
                    "strategy_type": "rsi_reversal",
                    "execution_mode": "signal_only",
                    "parameters": {"rsi_period": 14, "oversold": 30, "overbought": 70, "position_pct": 0.1},
                },
            },
            {
                "key": "momentum_macd_follow",
                "name": "动量跟随观察",
                "category": "momentum",
                "description": "使用 MACD 跟踪动量强化和转弱信号，强调先做历史与纸面验证。",
                "scenario": "适合中期动量延续的标的，用来观察趋势是否继续扩张。",
                "fit_for": ["趋势延续", "动量确认", "准备后续回测"],
                "not_fit_for": ["消息面剧烈扰动", "极短线抢跑", "缺少连续日线样本"],
                "risk_note": str(macd_meta["risk_note"]),
                "minimum_history": int(macd_meta["minimum_history"]),
                "auto_trade_allowed": bool(macd_meta["auto_trade_allowed"]),
                "research_only": False,
                "parameter_bounds": self._parameter_bounds(list(macd_meta["parameter_schema"])),
                "payload": {
                    "name": "动量跟随观察",
                    "symbol": "600519.SH",
                    "strategy_type": "macd",
                    "execution_mode": "signal_only",
                    "parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9, "position_pct": 0.1},
                },
            },
            {
                "key": "grid_research_placeholder",
                "name": "网格研究模板",
                "category": "grid",
                "description": "当前仓库未提供稳定网格执行主路径，本模板仅用于研究占位和参数讨论。",
                "scenario": "适合先记录假设与参数边界，不进入自动纸面交易。",
                "fit_for": ["区间震荡研究", "参数占位", "后续人工实现前的说明"],
                "not_fit_for": ["当前自动执行", "收益暗示", "无人工复核直接使用"],
                "risk_note": "研究占位模板，不生成稳定自动交易信号。",
                "minimum_history": 60,
                "auto_trade_allowed": False,
                "research_only": True,
                "parameter_bounds": {
                    "grid_step_pct": {"type": "number", "minimum": 0.005, "maximum": 0.1, "default": 0.02, "enum": [], "description": "网格间距"},
                    "grid_levels": {"type": "integer", "minimum": 2, "maximum": 20, "default": 6, "enum": [], "description": "网格层数"},
                },
                "payload": {
                    "name": "网格研究模板",
                    "symbol": "600519.SH",
                    "strategy_type": "moving_average",
                    "execution_mode": "signal_only",
                    "parameters": {"short_window": 5, "long_window": 20, "position_pct": 0.0, "template_mode": "research_grid"},
                },
            },
            {
                "key": "factor_scoring_fusion",
                "name": "因子打分研究",
                "category": "factor_scoring",
                "description": "复用多信号融合做可解释因子/信号打分，不承诺形成完整因子平台。",
                "scenario": "适合研究不同子信号贡献和冲突，不直接自动下单。",
                "fit_for": ["可解释研究", "子信号权重观察", "信号排序讨论"],
                "not_fit_for": ["完整分组回测平台", "自动实盘", "覆盖原始行情字段"],
                "risk_note": str(fusion_meta["risk_note"]),
                "minimum_history": int(fusion_meta["minimum_history"]),
                "auto_trade_allowed": False,
                "research_only": False,
                "parameter_bounds": self._parameter_bounds(list(fusion_meta["parameter_schema"])),
                "payload": {
                    "name": "因子打分研究",
                    "symbol": "600519.SH",
                    "strategy_type": "signal_fusion",
                    "execution_mode": "signal_only",
                    "parameters": {
                        "min_confidence": 0.55,
                        "conflict_hold_threshold": 0.2,
                        "position_pct": 0.1,
                    },
                },
            },
            {
                "key": "portfolio_rebalance_rl_research",
                "name": "组合再平衡研究",
                "category": "portfolio_rebalance",
                "description": "以 RL 基线作为组合再平衡研究占位，不引入新的执行引擎。",
                "scenario": "适合做研究回放和仓位切换讨论，不自动交易。",
                "fit_for": ["研究回放", "仓位切换讨论", "RL 接入前基线比较"],
                "not_fit_for": ["生产级再平衡", "自动实盘", "缺少模型校验"],
                "risk_note": str(rl_meta["risk_note"]),
                "minimum_history": int(rl_meta["minimum_history"]),
                "auto_trade_allowed": False,
                "research_only": True,
                "parameter_bounds": self._parameter_bounds(list(rl_meta["parameter_schema"])),
                "payload": {
                    "name": "组合再平衡研究",
                    "symbol": "600519.SH",
                    "strategy_type": "rl_trading",
                    "execution_mode": "signal_only",
                    "parameters": {"rl_policy_mode": "baseline", "max_position_pct": 0.5, "min_confidence": 0.1},
                },
            },
        ]

    def _current_strategy_readiness(self, db: Session, strategy: Strategy) -> tuple[str, str]:
        latest_run = db.scalar(
            select(StrategyRun)
            .where(StrategyRun.strategy_id == strategy.id)
            .order_by(StrategyRun.created_at.desc(), StrategyRun.id.desc())
            .limit(1)
        )
        total_run_count = db.scalar(select(func.count(StrategyRun.id)).where(StrategyRun.strategy_id == strategy.id)) or 0
        latest_run_status = latest_run.status.value if latest_run is not None else None
        return self._strategy_readiness(
            strategy,
            total_run_count=int(total_run_count),
            latest_run_status=latest_run_status,
            user_id=strategy.user_id,
        )

    def _strategy_overview(self, strategy: Strategy) -> dict[str, Any]:
        plugin = self.plugin_registry.get(strategy.strategy_type.value)
        return self._plugin_metadata(plugin, self._runtime_strategy_parameters(strategy))

    def _strategy_readiness(self, strategy: Strategy, *, total_run_count: int, latest_run_status: str | None, user_id: int | None = None) -> tuple[str, str]:
        if strategy.status == StrategyStatus.PAUSED:
            return STRATEGY_READINESS_PAUSED, "策略已暂停"
        overview = self._strategy_overview(strategy)
        parameters = strategy.parameters or {}
        validation_errors = self._validate_strategy_parameters(strategy.strategy_type, parameters, user_id=user_id, raise_on_error=False)
        if validation_errors:
            return STRATEGY_READINESS_DRAFT, validation_errors[0]
        if total_run_count < 3:
            return STRATEGY_READINESS_OBSERVING, "仍在观察期，需至少 3 次纸面运行"
        if latest_run_status is None:
            return STRATEGY_READINESS_OBSERVING, "缺少纸面运行结果"
        if strategy.execution_mode == StrategyExecutionMode.AUTO_TRADE and not overview["auto_trade_allowed"]:
            return STRATEGY_READINESS_OBSERVING, "RL 策略默认不允许自动交易"
        return STRATEGY_READINESS_PAPER_VERIFIED, "已通过纸面验证"

    def _normalize_strategy_parameters(self, strategy_type: StrategyType, parameters: dict[str, Any], *, user_id: int | None = None) -> dict[str, Any]:
        normalized = dict(parameters or {})
        if strategy_type == StrategyType.MOVING_AVERAGE:
            normalized["short_window"] = int(normalized.get("short_window", 5))
            normalized["long_window"] = int(normalized.get("long_window", 20))
        elif strategy_type == StrategyType.MACD:
            normalized["fast_period"] = int(normalized.get("fast_period", 12))
            normalized["slow_period"] = int(normalized.get("slow_period", 26))
            normalized["signal_period"] = int(normalized.get("signal_period", 9))
        elif strategy_type == StrategyType.RL_TRADING:
            normalized["rl_policy_mode"] = str(normalized.get("rl_policy_mode", "baseline"))
        elif strategy_type == StrategyType.RSI_REVERSAL:
            normalized["rsi_period"] = int(normalized.get("rsi_period", 14))
            normalized["oversold"] = float(normalized.get("oversold", 30))
            normalized["overbought"] = float(normalized.get("overbought", 70))
        elif strategy_type == StrategyType.BOLLINGER_BAND:
            normalized["boll_period"] = int(normalized.get("boll_period", 20))
            normalized["stddev_multiplier"] = float(normalized.get("stddev_multiplier", 2))
        elif strategy_type == StrategyType.KDJ_MOMENTUM:
            normalized["kdj_period"] = int(normalized.get("kdj_period", 9))
            normalized["k_smoothing"] = int(normalized.get("k_smoothing", 3))
            normalized["d_smoothing"] = int(normalized.get("d_smoothing", 3))
        elif strategy_type == StrategyType.SIGNAL_FUSION:
            normalized["min_confidence"] = float(normalized.get("min_confidence", 0.55))
            normalized["conflict_hold_threshold"] = float(normalized.get("conflict_hold_threshold", 0.2))
            normalized.setdefault("components", [
                {"strategy_type": "rsi_reversal", "weight": 1, "parameters": {"rsi_period": 14, "oversold": 30, "overbought": 70, "position_pct": 0.1}},
                {"strategy_type": "bollinger_band", "weight": 1, "parameters": {"boll_period": 20, "stddev_multiplier": 2, "position_pct": 0.1}},
            ])
        return normalized

    def _validate_strategy_parameters(
        self,
        strategy_type: StrategyType,
        parameters: dict[str, Any],
        *,
        user_id: int | None = None,
        raise_on_error: bool = True,
    ) -> list[str]:
        normalized = dict(parameters or {})
        errors: list[str] = []

        def fail(message: str) -> None:
            errors.append(message)

        if strategy_type == StrategyType.MOVING_AVERAGE:
            short_window = int(normalized.get("short_window", 5))
            long_window = int(normalized.get("long_window", 20))
            if short_window < 2:
                fail("short_window must be at least 2")
            if long_window <= short_window:
                fail("long_window must be greater than short_window")
        elif strategy_type == StrategyType.MACD:
            fast_period = int(normalized.get("fast_period", 12))
            slow_period = int(normalized.get("slow_period", 26))
            signal_period = int(normalized.get("signal_period", 9))
            if fast_period < 2:
                fail("fast_period must be at least 2")
            if slow_period <= fast_period:
                fail("slow_period must be greater than fast_period")
            if signal_period < 2:
                fail("signal_period must be at least 2")
        elif strategy_type == StrategyType.RL_TRADING:
            policy_mode = str(normalized.get("rl_policy_mode", "baseline"))
            if policy_mode == "trained_model":
                model_id = str(normalized.get("model_id") or "").strip()
                if not model_id:
                    fail("trained_model requires model_id")
                else:
                    from app.quant.training import RLModelRegistry

                    artifact = RLModelRegistry(self._rl_model_registry_root(user_id)).load(model_id)
                    if artifact is None:
                        fail("trained_model model_id not found")
                    elif artifact.get("status") not in {"validated", "active"}:
                        fail("trained_model model status is not validated or active")
        elif strategy_type == StrategyType.RSI_REVERSAL:
            rsi_period = int(normalized.get("rsi_period", 14))
            oversold = float(normalized.get("oversold", 30))
            overbought = float(normalized.get("overbought", 70))
            if rsi_period < 2:
                fail("rsi_period must be at least 2")
            if not 0 <= oversold < overbought <= 100:
                fail("oversold must be less than overbought and both must be within 0-100")
        elif strategy_type == StrategyType.BOLLINGER_BAND:
            boll_period = int(normalized.get("boll_period", 20))
            stddev_multiplier = float(normalized.get("stddev_multiplier", 2))
            if boll_period < 2:
                fail("boll_period must be at least 2")
            if stddev_multiplier <= 0:
                fail("stddev_multiplier must be greater than 0")
        elif strategy_type == StrategyType.KDJ_MOMENTUM:
            kdj_period = int(normalized.get("kdj_period", 9))
            k_smoothing = int(normalized.get("k_smoothing", 3))
            d_smoothing = int(normalized.get("d_smoothing", 3))
            if kdj_period < 2:
                fail("kdj_period must be at least 2")
            if k_smoothing < 1 or d_smoothing < 1:
                fail("kdj smoothing values must be at least 1")
        elif strategy_type == StrategyType.SIGNAL_FUSION:
            components = normalized.get("components")
            if not isinstance(components, list) or not components:
                fail("signal_fusion requires at least one component")
            else:
                allowed_components = {StrategyType.RSI_REVERSAL.value, StrategyType.BOLLINGER_BAND.value, StrategyType.KDJ_MOMENTUM.value}
                for component in components:
                    if not isinstance(component, dict):
                        fail("signal_fusion components must be objects")
                        continue
                    component_type = str(component.get("strategy_type") or "")
                    if component_type not in allowed_components:
                        fail(f"unsupported fusion component: {component_type}")
                    if float(component.get("weight", 1) or 0) < 0:
                        fail("fusion component weight must be non-negative")
            min_confidence = float(normalized.get("min_confidence", 0.55))
            conflict_hold_threshold = float(normalized.get("conflict_hold_threshold", 0.2))
            if not 0 <= min_confidence <= 1:
                fail("min_confidence must be within 0-1")
            if not 0 <= conflict_hold_threshold <= 1:
                fail("conflict_hold_threshold must be within 0-1")
        if errors and raise_on_error:
            raise HTTPException(status_code=422, detail={"message": "invalid strategy parameters", "errors": errors})
        return errors

    @staticmethod
    def _rl_model_registry_root(user_id: int | None) -> Path | None:
        if user_id is None:
            return None
        return Path(__file__).resolve().parents[3] / "artifacts" / "rl_models" / f"user-{user_id}"

    def _load_price_bars(self, symbol: str, limit: int) -> list[DailyBarSnapshot]:
        return self.market_data_service.get_daily_bars(symbol, limit=limit)

    def _required_history_limit(self, strategy: Strategy) -> int:
        plugin = self.plugin_registry.get(strategy.strategy_type.value)
        return plugin.minimum_history(self._runtime_strategy_parameters(strategy))

    def _resolve_execution_price(self, symbol: str, signal: dict[str, Any]) -> tuple[float, dict[str, float | bool]]:
        quote = self.trading_service._get_quote_snapshot(symbol)
        quote_price = float(quote.get("price", 0.0) or 0.0)
        if quote_price > 0:
            return quote_price, quote

        fallback_price = self._as_float(signal.get("entry_price_ref")) or 0.0
        return fallback_price, quote

    def _sync_position_exit_guard_from_signal(
        self,
        db: Session,
        symbol: str,
        signal: dict[str, Any],
        *,
        signal_type: str,
        user_id: int | None = None,
    ) -> None:
        if signal_type not in {"buy", "hold", "reduce"}:
            return

        position = self._get_position(db, symbol, user_id)
        if position is None or position.quantity <= 0:
            return

        stop_loss_price = self._as_float(signal.get("stop_loss_price"))
        take_profit_price = self._as_float(signal.get("take_profit_price"))
        if stop_loss_price is None and take_profit_price is None:
            return

        position.stop_loss_price = (
            Decimal(str(stop_loss_price)).quantize(PRICE_QUANTUM)
            if stop_loss_price is not None
            else None
        )
        position.take_profit_price = (
            Decimal(str(take_profit_price)).quantize(PRICE_QUANTUM)
            if take_profit_price is not None
            else None
        )
        position.exit_guard_status = "active"
        position.exit_trigger_reason = None
        position.exit_triggered_at = None
        db.flush()

    def _resolve_recommendation_snapshot(
        self,
        db: Session,
        symbol: str,
        *,
        now: datetime | None = None,
        user_id: int | None = None,
    ) -> RecommendationSnapshotContext:
        reference_day = market_trade_date(now)
        previous_day = previous_trading_day(reference_day)
        latest_by_trade_day: dict[date, SmartSelectionRun] = {}
        has_expired_snapshot = False

        runs = db.scalars(
            select(SmartSelectionRun)
            .where(
                SmartSelectionRun.tenant_id == settings.default_tenant_id,
                or_(SmartSelectionRun.user_id == user_id, SmartSelectionRun.user_id.is_(None)),
                SmartSelectionRun.status == SmartSelectionRunStatus.SUCCEEDED,
            )
            .order_by(desc(SmartSelectionRun.started_at), desc(SmartSelectionRun.id))
        ).all()

        for run in runs:
            snapshot_at = self._recommendation_snapshot_datetime(run)
            if snapshot_at is None:
                continue
            snapshot_day = market_trade_date(snapshot_at)
            if snapshot_day not in latest_by_trade_day:
                latest_by_trade_day[snapshot_day] = run
            if snapshot_day < previous_day:
                has_expired_snapshot = True

        for target_day in (reference_day, previous_day):
            run = latest_by_trade_day.get(target_day)
            if run is None:
                continue
            item = db.scalar(
                select(SmartSelectionItem)
                .where(
                    SmartSelectionItem.run_id == run.id,
                    SmartSelectionItem.symbol == symbol,
                )
                .order_by(desc(SmartSelectionItem.score), SmartSelectionItem.id.asc())
                .limit(1)
            )
            return RecommendationSnapshotContext(item=item, snapshot_date=target_day)

        return RecommendationSnapshotContext(item=None, snapshot_date=None, snapshot_expired=has_expired_snapshot)

    @staticmethod
    def _is_special_attention_watchlist_symbol(db: Session, symbol: str, user_id: int | None = None) -> bool:
        item = db.scalar(
            select(WatchlistItem.id).where(
                WatchlistItem.tenant_id == settings.default_tenant_id,
                or_(WatchlistItem.user_id == user_id, WatchlistItem.user_id.is_(None)),
                WatchlistItem.symbol == symbol,
                WatchlistItem.is_special_attention.is_(True),
            )
        )
        return item is not None

    def _recommendation_position_pct(self, recommendation: SmartSelectionItem) -> float:
        raw_position_pct = (recommendation.raw_detail or {}).get("position_pct")
        try:
            numeric = float(raw_position_pct)
        except (TypeError, ValueError):
            numeric = 10.0
        if numeric > 1:
            numeric = numeric / 100
        return max(0.01, min(numeric, 1.0))

    def _calculate_buy_quantity(
        self,
        *,
        account: Account,
        price: float,
        position_pct: float,
        current_position_value: float,
        total_position_value: float,
    ) -> int:
        if price <= 0 or position_pct <= 0:
            return 0

        total_equity = float(account.total_equity)
        max_position_budget = total_equity * position_pct
        target_position_room = max(max_position_budget - current_position_value, 0.0)
        single_position_room = max(total_equity * 0.2 - current_position_value, 0.0)
        total_exposure_room = max(total_equity * 0.9 - total_position_value, 0.0)
        budget = min(float(account.available_cash), target_position_room, single_position_room, total_exposure_room)
        if budget <= 0:
            return 0
        return int((budget // price) // 100 * 100)

    @staticmethod
    def _calculate_sell_quantity(*, available_quantity: int, signal_type: str, position_pct: float) -> int:
        sellable_lots = (available_quantity // 100) * 100
        if sellable_lots < 100:
            return 0
        if signal_type == "sell":
            return sellable_lots
        desired = int((available_quantity * position_pct) // 100 * 100)
        return min(sellable_lots, max(desired, 100))

    def _preflight_risk_blockers(
        self,
        db: Session,
        *,
        account: Account,
        position: Position | None,
        side: str,
        quantity: int,
        price: float,
        current_position_value: float,
        total_position_value: float,
        quote: dict[str, float | bool],
    ) -> list[str]:
        if quantity < 100 or price <= 0:
            return []

        risk_result = self.trading_service._validate_for_execution(
            db,
            account=account,
            position=position,
            side=side,
            quantity=quantity,
            price_decimal=Decimal(str(price)),
            current_position_value=Decimal(str(current_position_value)),
            total_position_value=Decimal(str(total_position_value)),
            quote=quote,
        )
        blockers = [
            self._map_rejection_reason(item.explanation)
            for item in risk_result.checks
            if not item.passed and item.explanation
        ]
        if not blockers and risk_result.rejection_reason:
            blockers.append(self._map_rejection_reason(risk_result.rejection_reason))
        return [blocker for blocker in blockers if blocker is not None]

    @staticmethod
    def _map_rejection_reason(value: Any) -> str | None:
        return normalize_reason_code(value)

    @staticmethod
    def _is_opening_trade_window(now: datetime | None = None) -> bool:
        return is_opening_buy_window(now)

    @staticmethod
    def _current_market_datetime() -> datetime:
        return market_now()

    @staticmethod
    def _recommendation_snapshot_datetime(run: SmartSelectionRun) -> datetime | None:
        return recommendation_snapshot_datetime(run)

    @staticmethod
    def _resolve_position_add_path(position: Position | None) -> str:
        if position is None or position.quantity <= 0:
            return "new_position"
        if position.strategy_add_count >= 1:
            return "blocked_repeat_add"
        return "first_add"

    @staticmethod
    def _serialize_date(value: date | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _db_datetime_trade_date(value: datetime) -> date:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return market_trade_date(value)

    def _resolve_target_symbols(self, db: Session, strategy: Strategy) -> list[str]:
        return self.target_resolver.resolve_symbols(db, strategy)

    def _ordered_special_attention_symbols(self, db: Session, user_id: int | None = None) -> list[str]:
        return self.target_resolver.ordered_special_attention_symbols(db, user_id)

    def _latest_recommendation_symbols(self, db: Session, *, now: datetime | None = None, user_id: int | None = None) -> list[str]:
        return self.target_resolver.latest_recommendation_symbols(db, now=now, user_id=user_id)

    def _open_position_symbols(self, db: Session, user_id: int | None = None) -> list[str]:
        return self.target_resolver.open_position_symbols(db, user_id)

    def _latest_recommendation_scope_run(
        self,
        db: Session,
        *,
        now: datetime | None = None,
        user_id: int | None = None,
    ) -> SmartSelectionRun | None:
        return self.target_resolver.latest_recommendation_scope_run(db, now=now, user_id=user_id)

    @staticmethod
    def _strategy_primary_symbol(strategy: Strategy) -> str:
        return StrategyTargetResolver.primary_symbol(strategy)

    def _strategy_target_label(self, strategy: Strategy, resolved_symbols: list[str] | None = None) -> str:
        return self.target_resolver.label(strategy, resolved_symbols)

    @staticmethod
    def _strategy_target_config(strategy: Strategy) -> dict[str, Any]:
        return StrategyTargetResolver.target_config(strategy)

    def _normalize_target_payload(
        self,
        symbol: str | None,
        target_type: str | None,
        target_config: dict[str, Any] | None,
    ) -> tuple[StrategyTargetType, dict[str, Any], str]:
        return self.target_resolver.normalize_payload(symbol, target_type, target_config)

    @staticmethod
    def _parse_strategy_type(raw_status: str) -> StrategyType:
        try:
            return StrategyType(raw_status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"unsupported strategy_type: {raw_status}") from exc

    @staticmethod
    def _parse_strategy_status(raw_status: str) -> StrategyStatus:
        try:
            return StrategyStatus(raw_status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"unsupported strategy status: {raw_status}") from exc

    @staticmethod
    def _parse_execution_mode(raw_mode: str) -> StrategyExecutionMode:
        try:
            return StrategyExecutionMode(raw_mode)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"unsupported execution_mode: {raw_mode}") from exc

    @staticmethod
    def _parse_target_type(raw_target_type: str) -> StrategyTargetType:
        return StrategyTargetResolver.parse_target_type(raw_target_type)

    @staticmethod
    def _get_strategy(db: Session, strategy_id: int, tenant_id: str, user_id: int | None = None) -> Strategy:
        strategy = db.scalar(
            select(Strategy).where(
                Strategy.id == strategy_id,
                Strategy.tenant_id == tenant_id,
                Strategy.user_id == user_id,
            )
        )
        if strategy is None or StrategyService._is_deleted(strategy):
            raise HTTPException(status_code=404, detail="strategy not found")
        return strategy

    @staticmethod
    def _is_deleted(strategy: Strategy) -> bool:
        return bool((strategy.parameters or {}).get("deleted_at"))

    @staticmethod
    def _get_default_account(db: Session, user_id: int | None = None) -> Account | None:
        query = select(Account).where(
            Account.tenant_id == settings.default_tenant_id,
            Account.name == settings.default_account_name,
        )
        if user_id is None:
            query = query.where(Account.user_id.is_(None))
        else:
            query = query.where(or_(Account.user_id == user_id, Account.user_id.is_(None))).order_by(Account.user_id.is_(None).asc())
        return db.scalar(query.limit(1))

    @staticmethod
    def _get_position(db: Session, symbol: str, user_id: int | None = None) -> Position | None:
        account = StrategyService._get_default_account(db, user_id)
        if account is None:
            return None
        return db.scalar(select(Position).where(Position.account_id == account.id, Position.symbol == symbol))

    @staticmethod
    def _has_pending_sell_order(db: Session, *, account_id: int, symbol: str) -> bool:
        pending_order_id = db.scalar(
            select(Order.id)
            .where(
                Order.account_id == account_id,
                Order.symbol == symbol,
                Order.side == OrderSide.SELL,
                Order.status == OrderStatus.PENDING,
            )
            .limit(1)
        )
        return pending_order_id is not None

    @staticmethod
    def _normalize_strength(value: Any) -> str:
        strength = str(value or "normal").lower()
        if strength not in {"strong", "normal", "weak"}:
            return "normal"
        return strength

    @staticmethod
    def _clamp_fraction(value: Any, *, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(numeric, 1.0))

    @staticmethod
    def _as_str(value: Any) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _as_bool(value: Any) -> bool | None:
        if value is None:
            return None
        return bool(value)

    @staticmethod
    def _as_str_list(value: Any) -> list[str]:
        if not value:
            return []
        return [str(item) for item in value]
