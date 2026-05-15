from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.event_log import EventLog, EventLogType


class EventLogService:
    def append(
        self,
        db: Session,
        *,
        tenant_id: str,
        event_type: EventLogType,
        payload: dict,
        user_id: int | None = None,
        account_id: int | None = None,
        symbol: str | None = None,
        occurred_at: datetime | None = None,
        strategy_id: int | None = None,
        strategy_run_id: int | None = None,
        order_id: int | None = None,
        order_event_id: int | None = None,
        trade_id: int | None = None,
        position_id: int | None = None,
        equity_snapshot_id: int | None = None,
        correlation_id: str | None = None,
        risk_rule_version: str | None = None,
    ) -> EventLog:
        event = EventLog(
            tenant_id=tenant_id,
            user_id=user_id,
            account_id=account_id,
            event_type=event_type,
            symbol=symbol,
            occurred_at=occurred_at or datetime.utcnow(),
            strategy_id=strategy_id,
            strategy_run_id=strategy_run_id,
            order_id=order_id,
            order_event_id=order_event_id,
            trade_id=trade_id,
            position_id=position_id,
            equity_snapshot_id=equity_snapshot_id,
            correlation_id=correlation_id,
            risk_rule_version=risk_rule_version,
            payload=payload,
        )
        db.add(event)
        db.flush()
        return event

    def query(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        strategy_id: int | None = None,
        strategy_run_id: int | None = None,
        order_id: int | None = None,
        symbol: str | None = None,
        event_type: str | None = None,
        correlation_id: str | None = None,
    ) -> list[EventLog]:
        query = select(EventLog)
        if user_id is not None:
            query = query.where(EventLog.user_id == user_id)
        if start_at is not None:
            query = query.where(EventLog.occurred_at >= start_at)
        if end_at is not None:
            query = query.where(EventLog.occurred_at <= end_at)
        if strategy_id is not None:
            query = query.where(EventLog.strategy_id == strategy_id)
        if strategy_run_id is not None:
            query = query.where(EventLog.strategy_run_id == strategy_run_id)
        if order_id is not None:
            query = query.where(EventLog.order_id == order_id)
        if symbol is not None:
            query = query.where(EventLog.symbol == symbol)
        if event_type is not None:
            query = query.where(EventLog.event_type == EventLogType(event_type))
        if correlation_id is not None:
            query = query.where(EventLog.correlation_id == correlation_id)
        return list(db.scalars(query.order_by(EventLog.occurred_at.asc(), EventLog.id.asc())).all())

    def facts_for_context(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        strategy_run_id: int | None = None,
        order_id: int | None = None,
        correlation_id: str | None = None,
    ) -> list[dict]:
        events = self.query(
            db,
            user_id=user_id,
            strategy_run_id=strategy_run_id,
            order_id=order_id,
            correlation_id=correlation_id,
        )
        return [
            {
                "event_type": event.event_type.value,
                "occurred_at": event.occurred_at.isoformat(),
                "symbol": event.symbol,
                "order_id": event.order_id,
                "trade_id": event.trade_id,
                "correlation_id": event.correlation_id,
                "payload": event.payload,
            }
            for event in events
        ]
