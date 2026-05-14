from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.strategy_run import StrategyRun
from app.models.strategy_run_item import StrategyRunItem
from app.market.security_names import security_name
from app.schemas.strategy import StrategyRunItemRead, StrategyRunRead
from app.strategy.contracts import StrategySignal


class StrategyRunReadBuilder:
    def __init__(
        self,
        *,
        as_str: Callable[[Any], str | None],
        as_int: Callable[[Any], int | None],
        as_float: Callable[[Any], float | None],
        as_bool: Callable[[Any], bool | None],
        as_str_list: Callable[[Any], list[str]],
    ) -> None:
        self._as_str = as_str
        self._as_int = as_int
        self._as_float = as_float
        self._as_bool = as_bool
        self._as_str_list = as_str_list

    def build_run_read(self, db: Session, run: StrategyRun) -> StrategyRunRead:
        signal = run.signal or {}
        standard_signal = dict(signal.get("standard_signal") or StrategySignal.coerce(signal).to_dict())
        items = db.scalars(
            select(StrategyRunItem)
            .where(StrategyRunItem.run_id == run.id)
            .order_by(StrategyRunItem.id.asc())
        ).all()
        return StrategyRunRead(
            id=run.id,
            strategy_id=run.strategy_id,
            status=run.status.value,
            signal={**signal, "standard_signal": standard_signal},
            execution_mode=self._as_str(signal.get("execution_mode")),
            order_submitted=bool(signal.get("order_submitted", False)),
            order_id=self._as_int(signal.get("order_id")),
            order_status=self._as_str(signal.get("order_status")),
            side=self._as_str(signal.get("side")),
            quantity=self._as_int(signal.get("quantity")),
            price=self._as_float(signal.get("price")),
            reason=self._as_str(signal.get("reason")),
            strength=self._as_str(signal.get("strength")),
            trigger_reason=self._as_str(signal.get("trigger_reason")),
            stop_loss_price=self._as_float(signal.get("stop_loss_price")),
            take_profit_price=self._as_float(signal.get("take_profit_price")),
            position_pct=self._as_float(signal.get("position_pct")),
            recommendation_confirmed=self._as_bool(signal.get("recommendation_confirmed")),
            confirmation_source=self._as_str(signal.get("confirmation_source")),
            recommendation_snapshot_date=self._as_str(signal.get("recommendation_snapshot_date")),
            position_add_path=self._as_str(signal.get("position_add_path")),
            execution_blockers=self._as_str_list(signal.get("execution_blockers")),
            items=[self.build_run_item_read(item) for item in items],
            created_at=as_utc_datetime(run.created_at),
        )

    def build_run_item_read(self, item: StrategyRunItem) -> StrategyRunItemRead:
        signal = item.signal or {}
        standard_signal = dict(signal.get("standard_signal") or StrategySignal.coerce(signal).to_dict())
        return StrategyRunItemRead(
            id=item.id,
            symbol=item.symbol,
            name=security_name(item.symbol),
            signal={**signal, "standard_signal": standard_signal},
            order_submitted=bool(signal.get("order_submitted", False)),
            order_id=self._as_int(signal.get("order_id")),
            order_status=self._as_str(signal.get("order_status")),
            side=self._as_str(signal.get("side")),
            quantity=self._as_int(signal.get("quantity")),
            price=self._as_float(signal.get("price")),
            reason=self._as_str(signal.get("reason")),
            strength=self._as_str(signal.get("strength")),
            trigger_reason=self._as_str(signal.get("trigger_reason")),
            stop_loss_price=self._as_float(signal.get("stop_loss_price")),
            take_profit_price=self._as_float(signal.get("take_profit_price")),
            position_pct=self._as_float(signal.get("position_pct")),
            recommendation_confirmed=self._as_bool(signal.get("recommendation_confirmed")),
            confirmation_source=self._as_str(signal.get("confirmation_source")),
            recommendation_snapshot_date=self._as_str(signal.get("recommendation_snapshot_date")),
            position_add_path=self._as_str(signal.get("position_add_path")),
            execution_blockers=self._as_str_list(signal.get("execution_blockers")),
            created_at=as_utc_datetime(item.created_at),
        )


def as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
