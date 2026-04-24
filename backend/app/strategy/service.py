from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import Account
from app.models.position import Position
from app.models.strategy import Strategy, StrategyExecutionMode, StrategyStatus, StrategyType
from app.models.strategy_run import StrategyRun, StrategyRunStatus
from app.schemas.strategy import StrategyCreate, StrategyRead, StrategyRunRead, StrategyUpdate
from app.strategy.base import StrategyPlugin
from app.strategy.strategies.macd import MacdStrategy
from app.strategy.strategies.moving_average import MovingAverageStrategy
from app.trading.service import TradingService

DEFAULT_PRICE_SERIES = {
    "sh600519": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
    "sz000001": [12, 11.9, 11.8, 11.7, 11.6, 11.5, 11.4, 11.3, 11.2, 11.1, 11.0, 10.9, 10.8, 10.7, 10.6, 10.5, 10.4, 10.3, 10.2, 10.1],
}


class StrategyService:
    def __init__(self) -> None:
        self.plugins: dict[str, StrategyPlugin] = {
            StrategyType.MOVING_AVERAGE.value: MovingAverageStrategy(),
            StrategyType.MACD.value: MacdStrategy(),
        }
        self.trading_service = TradingService()

    def list_strategies(self, db: Session, tenant_id: str = settings.default_tenant_id) -> list[StrategyRead]:
        strategies = db.scalars(
            select(Strategy)
            .where(Strategy.tenant_id == tenant_id)
            .order_by(Strategy.created_at.asc(), Strategy.id.asc())
        ).all()
        return [self._build_strategy_read(db, strategy) for strategy in strategies]

    def create_strategy(
        self,
        db: Session,
        payload: StrategyCreate,
        tenant_id: str = settings.default_tenant_id,
    ) -> StrategyRead:
        strategy_type = self._parse_strategy_type(payload.strategy_type)
        strategy = Strategy(
            tenant_id=tenant_id,
            name=payload.name.strip(),
            symbol=payload.symbol.strip().lower(),
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
        if payload.symbol is not None:
            strategy.symbol = payload.symbol.strip().lower()
        if payload.strategy_type is not None:
            strategy.strategy_type = self._parse_strategy_type(payload.strategy_type)
        if payload.status is not None:
            strategy.status = self._parse_strategy_status(payload.status)
        if payload.execution_mode is not None:
            strategy.execution_mode = self._parse_execution_mode(payload.execution_mode)
        if payload.parameters is not None:
            strategy.parameters = payload.parameters

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
            signal = self._evaluate_strategy(strategy)
            run.status = StrategyRunStatus.SUCCESS
            run.signal = self._build_execution_signal(db, strategy, signal)
        except Exception as exc:
            run.status = StrategyRunStatus.FAILED
            run.signal = {"error": str(exc), "signal": "hold", "symbol": strategy.symbol}

        db.commit()
        db.refresh(run)
        return self._build_run_read(run)

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
        return [
            self.run_strategy(db, strategy.id, tenant_id)
            for strategy in strategies
        ]

    def _build_strategy_read(self, db: Session, strategy: Strategy) -> StrategyRead:
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
        latest_run_status = None
        latest_run_at = None
        if latest_run is not None:
            latest_run_status = latest_run.status.value
            latest_run_at = latest_run.created_at
            latest_signal = str(latest_run.signal.get("signal", "hold"))

        return StrategyRead(
            id=strategy.id,
            tenant_id=strategy.tenant_id,
            name=strategy.name,
            symbol=strategy.symbol,
            strategy_type=strategy.strategy_type.value,
            status=strategy.status.value,
            execution_mode=strategy.execution_mode.value,
            parameters=strategy.parameters,
            latest_signal=latest_signal,
            signal_symbol=strategy.symbol,
            latest_run_status=latest_run_status,
            latest_run_at=latest_run_at,
            run_count_today=int(run_count_today),
            total_run_count=int(total_run_count),
        )

    def _evaluate_strategy(self, strategy: Strategy) -> dict[str, Any]:
        plugin = self.plugins.get(strategy.strategy_type.value)
        if plugin is None:
            raise ValueError(f"unsupported strategy type: {strategy.strategy_type.value}")

        prices = DEFAULT_PRICE_SERIES.get(strategy.symbol)
        if prices is None:
            prices = self._fallback_price_series(strategy.symbol)
        return plugin.evaluate(strategy.symbol, prices, strategy.parameters)

    def _build_execution_signal(self, db: Session, strategy: Strategy, signal: dict[str, Any]) -> dict[str, Any]:
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
        }
        if strategy.execution_mode == StrategyExecutionMode.SIGNAL_ONLY:
            signal_payload["reason"] = "signal_only_mode"
            return signal_payload

        raw_signal = str(signal.get("signal", "hold"))
        if raw_signal not in {"buy", "sell"}:
            signal_payload["reason"] = "signal_hold"
            return signal_payload

        price = self._resolve_execution_price(strategy)
        quantity = self._calculate_order_quantity(db, strategy, raw_signal, price)
        signal_payload["side"] = raw_signal
        signal_payload["price"] = price
        signal_payload["quantity"] = quantity

        if quantity < 100:
            signal_payload["reason"] = "quantity_below_min_lot"
            return signal_payload

        order_result = self.trading_service.place_order(
            db,
            symbol=strategy.symbol,
            side=raw_signal,
            order_type="market",
            quantity=quantity,
            price=price,
            note_prefix=f"strategy {strategy.id}",
        )
        order_payload = order_result.get("order", {})
        signal_payload["order_submitted"] = True
        signal_payload["order_id"] = order_payload.get("id")
        signal_payload["order_status"] = order_payload.get("status")
        signal_payload["reason"] = str(order_result.get("rejection_reason") or order_payload.get("reject_reason") or order_result["status"])
        signal_payload["quantity"] = int(order_payload.get("quantity", quantity))
        signal_payload["price"] = float(order_payload.get("price", price))
        return signal_payload

    def _build_run_read(self, run: StrategyRun) -> StrategyRunRead:
        signal = run.signal or {}
        return StrategyRunRead(
            id=run.id,
            strategy_id=run.strategy_id,
            status=run.status.value,
            signal=signal,
            execution_mode=self._as_str(signal.get("execution_mode")),
            order_submitted=bool(signal.get("order_submitted", False)),
            order_id=self._as_int(signal.get("order_id")),
            order_status=self._as_str(signal.get("order_status")),
            side=self._as_str(signal.get("side")),
            quantity=self._as_int(signal.get("quantity")),
            price=self._as_float(signal.get("price")),
            reason=self._as_str(signal.get("reason")),
            created_at=run.created_at,
        )

    def _calculate_order_quantity(self, db: Session, strategy: Strategy, side: str, price: float) -> int:
        position_pct = float(strategy.parameters.get("position_pct", 0.1))
        position_pct = max(min(position_pct, 1.0), 0.0)
        if position_pct <= 0:
            return 0

        if side == "buy":
            account = self._get_default_account(db)
            if account is None:
                return 0
            budget = float(account.available_cash) * position_pct
            return int(budget // price // 100 * 100)

        position = self._get_position(db, strategy.symbol)
        if position is None or position.available_quantity < 100:
            return 0
        return max(int(position.available_quantity * position_pct // 100 * 100), 100)

    def _resolve_execution_price(self, strategy: Strategy) -> float:
        prices = DEFAULT_PRICE_SERIES.get(strategy.symbol)
        if prices is None:
            prices = self._fallback_price_series(strategy.symbol)
        return float(prices[-1])

    @staticmethod
    def _fallback_price_series(symbol: str) -> list[float]:
        if symbol.startswith("sz"):
            base_price = 10.0
        else:
            base_price = 100.0
        return [base_price + offset * 0.2 for offset in range(30)]

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
