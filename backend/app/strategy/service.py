from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.trading_calendar import is_opening_buy_window, market_now, market_trade_date, previous_trading_day
from app.market.data_service import MarketDataService
from app.market.providers.base import DailyBarSnapshot
from app.models.account import Account
from app.models.order import Order, OrderSide, OrderStatus
from app.models.position import Position
from app.models.smart_selection_item import SmartSelectionItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus
from app.models.strategy import Strategy, StrategyExecutionMode, StrategyStatus, StrategyTargetType, StrategyType
from app.models.strategy_run import StrategyRun, StrategyRunStatus
from app.market.security_names import security_display
from app.models.strategy_run_item import StrategyRunItem
from app.models.watchlist import WatchlistItem
from app.schemas.strategy import StrategyCreate, StrategyRead, StrategyRunItemRead, StrategyRunRead, StrategyUpdate
from app.strategy.dto import StrategyRunReadBuilder, as_utc_datetime
from app.strategy.plugins import StrategyPluginRegistry
from app.strategy.targets import StrategyTargetResolver, recommendation_snapshot_datetime
from app.trading.service import TradingService

RECOMMENDATION_ALLOWED_TIMINGS = {"BUY", "STRONG BUY"}
MIN_RECOMMENDATION_SCORE = 60.0
PRICE_QUANTUM = Decimal("0.0001")

REJECTION_REASON_CODES = {
    "outside trading hours": "outside_trading_hours",
    "symbol halted": "symbol_halted",
    "daily trade limit exceeded": "daily_trade_limit_exceeded",
    "single position limit exceeded": "single_position_limit_exceeded",
    "total exposure limit exceeded": "total_exposure_limit_exceeded",
    "daily loss circuit breaker triggered": "daily_loss_circuit_breaker",
    "insufficient cash": "insufficient_cash",
    "symbol at limit up": "limit_up_restriction",
    "symbol at limit down": "limit_down_restriction",
    "insufficient position": "insufficient_position",
    "t+1 sell restriction": "t_plus_one_restriction",
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

    def list_strategies(self, db: Session, tenant_id: str = settings.default_tenant_id) -> list[StrategyRead]:
        strategies = db.scalars(
            select(Strategy)
            .where(Strategy.tenant_id == tenant_id)
            .order_by(Strategy.created_at.asc(), Strategy.id.asc())
        ).all()
        return [self._build_strategy_read(db, strategy) for strategy in strategies]

    def get_latest_run(
        self,
        db: Session,
        *,
        strategy_id: int | None = None,
        tenant_id: str = settings.default_tenant_id,
    ) -> StrategyRunRead | None:
        query = (
            select(StrategyRun)
            .where(StrategyRun.tenant_id == tenant_id)
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
    ) -> list[StrategyRunRead]:
        query = (
            select(StrategyRun)
            .where(StrategyRun.tenant_id == tenant_id)
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
    ) -> StrategyRead:
        strategy_type = self._parse_strategy_type(payload.strategy_type)
        target_type, target_config, symbol = self._normalize_target_payload(
            payload.symbol,
            payload.target_type,
            payload.target_config,
        )
        strategy = Strategy(
            tenant_id=tenant_id,
            name=payload.name.strip(),
            symbol=symbol,
            target_type=target_type,
            target_config=target_config,
            strategy_type=strategy_type,
            status=StrategyStatus.DRAFT,
            execution_mode=self._parse_execution_mode(payload.execution_mode),
            parameters=payload.parameters,
        )
        db.add(strategy)
        db.commit()
        db.refresh(strategy)
        return self._build_strategy_read(db, strategy)

    def update_strategy(
        self,
        db: Session,
        strategy_id: int,
        payload: StrategyUpdate,
        tenant_id: str = settings.default_tenant_id,
    ) -> StrategyRead:
        strategy = self._get_strategy(db, strategy_id, tenant_id)

        if payload.name is not None:
            strategy.name = payload.name.strip()
        if payload.strategy_type is not None:
            strategy.strategy_type = self._parse_strategy_type(payload.strategy_type)
        if payload.status is not None:
            strategy.status = self._parse_strategy_status(payload.status)
        if payload.execution_mode is not None:
            strategy.execution_mode = self._parse_execution_mode(payload.execution_mode)
        if payload.parameters is not None:
            strategy.parameters = payload.parameters
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
        return self._build_strategy_read(db, strategy)

    def run_strategy(
        self,
        db: Session,
        strategy_id: int,
        tenant_id: str = settings.default_tenant_id,
    ) -> StrategyRunRead:
        strategy = self._get_strategy(db, strategy_id, tenant_id)
        run = StrategyRun(
            tenant_id=tenant_id,
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
                    signal = self._run_strategy_for_symbol(db, strategy, symbol)
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
    ) -> list[StrategyRunRead]:
        query = (
            select(Strategy)
            .where(
                Strategy.tenant_id == tenant_id,
                Strategy.status == StrategyStatus.ACTIVE,
            )
            .order_by(Strategy.created_at.asc(), Strategy.id.asc())
        )
        if strategy_ids is not None:
            if not strategy_ids:
                return []
            query = query.where(Strategy.id.in_(strategy_ids))

        strategies = db.scalars(query).all()
        return [self.run_strategy(db, strategy.id, tenant_id) for strategy in strategies]

    def _build_strategy_read(self, db: Session, strategy: Strategy) -> StrategyRead:
        resolved_symbols = self._resolve_target_symbols(db, strategy)
        signal_symbol = self._strategy_target_label(strategy, resolved_symbols)
        latest_run = db.scalar(
            select(StrategyRun)
            .where(StrategyRun.strategy_id == strategy.id)
            .order_by(StrategyRun.created_at.desc(), StrategyRun.id.desc())
            .limit(1)
        )
        today = date.today()
        run_count_today = db.scalar(
            select(func.count(StrategyRun.id)).where(
                StrategyRun.strategy_id == strategy.id,
                func.date(StrategyRun.created_at) == today,
            )
        ) or 0
        total_run_count = db.scalar(
            select(func.count(StrategyRun.id)).where(StrategyRun.strategy_id == strategy.id)
        ) or 0

        latest_signal = "hold"
        latest_signal_summary = None
        latest_run_status = None
        latest_run_at = None
        if latest_run is not None:
            latest_run_status = latest_run.status.value
            latest_run_at = self._as_utc_datetime(latest_run.created_at)
            latest_signal = str((latest_run.signal or {}).get("signal", "hold"))
            latest_signal_summary = self._build_signal_summary(latest_run.signal or {})

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
            signal_symbol=signal_symbol,
            signal_symbol_display=self._strategy_target_display_label(strategy, resolved_symbols, signal_symbol),
            resolved_target_count=len(resolved_symbols),
            latest_run_status=latest_run_status,
            latest_run_at=latest_run_at,
            run_count_today=int(run_count_today),
            total_run_count=int(total_run_count),
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
            )

        return self._normalize_signal(
            symbol=symbol,
            strategy_name=strategy.strategy_type.value,
            signal=plugin.evaluate(symbol, bars, strategy.parameters),
            parameters=strategy.parameters,
        )

    def _build_execution_signal(self, db: Session, strategy: Strategy, signal: dict[str, Any], *, symbol: str) -> dict[str, Any]:
        signal_payload = {
            **signal,
            "execution_mode": strategy.execution_mode.value,
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
        }

        if strategy.execution_mode == StrategyExecutionMode.SIGNAL_ONLY:
            signal_payload["reason"] = "signal_only_mode"
            signal_payload["execution_blockers"] = ["signal_only_mode"]
            return signal_payload

        raw_signal = str(signal_payload.get("signal", "hold"))
        if raw_signal == "hold":
            self._sync_position_exit_guard_from_signal(db, symbol, signal_payload, signal_type=raw_signal)
            signal_payload["reason"] = "signal_hold"
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
        self._sync_position_exit_guard_from_signal(db, symbol, signal_payload, signal_type=raw_signal)

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

    def _build_run_read(self, db: Session, run: StrategyRun) -> StrategyRunRead:
        return self.run_read_builder.build_run_read(db, run)

    def _build_run_item_read(self, item: StrategyRunItem) -> StrategyRunItemRead:
        return self.run_read_builder.build_run_item_read(item)

    @staticmethod
    def _as_utc_datetime(value: datetime) -> datetime:
        return as_utc_datetime(value)

    def _run_strategy_for_symbol(self, db: Session, strategy: Strategy, symbol: str) -> dict[str, Any]:
        try:
            signal = self._evaluate_strategy(strategy, symbol)
            return self._build_execution_signal(db, strategy, signal, symbol=symbol)
        except Exception as exc:
            payload = self._base_hold_signal(
                symbol=symbol,
                strategy_name=strategy.strategy_type.value,
                trigger_reason="strategy_run_failed",
                entry_price_ref=None,
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
        return payload

    def _build_no_target_signal(self, strategy: Strategy) -> dict[str, Any]:
        payload = self._base_hold_signal(
            symbol=self._strategy_primary_symbol(strategy),
            strategy_name=strategy.strategy_type.value,
            trigger_reason="no_target_symbols",
            entry_price_ref=None,
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
            }
        )
        return payload

    def _build_open_execution_plan(self, db: Session, strategy: Strategy, signal: dict[str, Any], *, symbol: str) -> ExecutionPlan:
        blockers: list[str] = []
        position = self._get_position(db, symbol)
        position_add_path = self._resolve_position_add_path(position)
        if position_add_path == "blocked_repeat_add":
            blockers.append("blocked_repeat_add")

        recommendation_context = self._resolve_recommendation_snapshot(
            db,
            symbol,
            now=self._current_market_datetime(),
        )
        recommendation = recommendation_context.item
        special_attention_confirmed = self._is_special_attention_watchlist_symbol(db, symbol)
        recommendation_score = None
        recommendation_timing = None
        bypass_recommendation_confirmation = bool(strategy.parameters.get("bypass_recommendation_confirmation", False))
        recommendation_confirmed = special_attention_confirmed or bypass_recommendation_confirmation
        confirmation_source = (
            "special_attention_watchlist"
            if special_attention_confirmed
            else "simulation_bypass"
            if bypass_recommendation_confirmation
            else "none"
        )
        recommendation_snapshot_date = None if special_attention_confirmed else self._serialize_date(recommendation_context.snapshot_date)

        signal_position_pct = self._clamp_fraction(signal.get("position_pct"), default=self._clamp_fraction(strategy.parameters.get("position_pct"), default=0.1))
        stop_loss_price = self._as_float(signal.get("stop_loss_price"))
        take_profit_price = self._as_float(signal.get("take_profit_price"))

        if not special_attention_confirmed and not bypass_recommendation_confirmation:
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

        account = self._get_default_account(db)
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
        account = self._get_default_account(db)
        position = self._get_position(db, symbol)

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
        }
        return payload

    def _base_hold_signal(
        self,
        *,
        symbol: str,
        strategy_name: str,
        trigger_reason: str,
        entry_price_ref: float | None,
    ) -> dict[str, Any]:
        return {
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
            "filter_passed": True,
            "filter_reasons": [],
            "trend_ok": None,
            "volume_ok": None,
            "volatility_ok": None,
            "stretch_ok": None,
            "market_regime_bias": None,
        }

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

    def _load_price_bars(self, symbol: str, limit: int) -> list[DailyBarSnapshot]:
        return self.market_data_service.get_daily_bars(symbol, limit=limit)

    def _required_history_limit(self, strategy: Strategy) -> int:
        if strategy.strategy_type == StrategyType.MOVING_AVERAGE:
            long_window = max(int(strategy.parameters.get("long_window", 20)), 20)
            return long_window + 10
        if strategy.strategy_type == StrategyType.RL_TRADING:
            long_window = max(int(strategy.parameters.get("ma_long_window", strategy.parameters.get("long_window", 20))), 20)
            return long_window + 20
        slow_period = max(int(strategy.parameters.get("slow_period", 26)), 26)
        signal_period = max(int(strategy.parameters.get("signal_period", 9)), 9)
        return slow_period + signal_period + 10

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
    ) -> None:
        if signal_type not in {"buy", "hold", "reduce"}:
            return

        position = self._get_position(db, symbol)
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
    ) -> RecommendationSnapshotContext:
        reference_day = market_trade_date(now)
        previous_day = previous_trading_day(reference_day)
        latest_by_trade_day: dict[date, SmartSelectionRun] = {}
        has_expired_snapshot = False

        runs = db.scalars(
            select(SmartSelectionRun)
            .where(
                SmartSelectionRun.tenant_id == settings.default_tenant_id,
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
    def _is_special_attention_watchlist_symbol(db: Session, symbol: str) -> bool:
        item = db.scalar(
            select(WatchlistItem.id).where(
                WatchlistItem.tenant_id == settings.default_tenant_id,
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
            self._map_rejection_reason(item.get("reason"))
            for item in risk_result.get("checks", [])
            if not item.get("passed") and item.get("reason")
        ]
        if not blockers and risk_result.get("rejection_reason"):
            blockers.append(self._map_rejection_reason(risk_result.get("rejection_reason")))
        return [blocker for blocker in blockers if blocker is not None]

    @staticmethod
    def _map_rejection_reason(value: Any) -> str | None:
        if value is None:
            return None
        reason = str(value)
        return REJECTION_REASON_CODES.get(reason, reason)

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

    def _resolve_target_symbols(self, db: Session, strategy: Strategy) -> list[str]:
        return self.target_resolver.resolve_symbols(db, strategy)

    def _ordered_special_attention_symbols(self, db: Session) -> list[str]:
        return self.target_resolver.ordered_special_attention_symbols(db)

    def _latest_recommendation_symbols(self, db: Session, *, now: datetime | None = None) -> list[str]:
        return self.target_resolver.latest_recommendation_symbols(db, now=now)

    def _latest_recommendation_scope_run(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> SmartSelectionRun | None:
        return self.target_resolver.latest_recommendation_scope_run(db, now=now)

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
    def _get_strategy(db: Session, strategy_id: int, tenant_id: str) -> Strategy:
        strategy = db.scalar(
            select(Strategy).where(
                Strategy.id == strategy_id,
                Strategy.tenant_id == tenant_id,
            )
        )
        if strategy is None:
            raise HTTPException(status_code=404, detail="strategy not found")
        return strategy

    @staticmethod
    def _get_default_account(db: Session) -> Account | None:
        return db.scalar(
            select(Account).where(
                Account.tenant_id == settings.default_tenant_id,
                Account.name == settings.default_account_name,
            )
        )

    @staticmethod
    def _get_position(db: Session, symbol: str) -> Position | None:
        account = StrategyService._get_default_account(db)
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
