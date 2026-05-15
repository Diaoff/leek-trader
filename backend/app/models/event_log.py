from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class EventLogType(StrEnum):
    STRATEGY_SIGNAL = "strategy_signal"
    RISK_DECISION = "risk_decision"
    ORDER_EVENT = "order_event"
    TRADE_EXECUTION = "trade_execution"
    POSITION_CHANGE = "position_change"
    EQUITY_SNAPSHOT = "equity_snapshot"


class EventLog(Base):
    __tablename__ = "event_logs"
    __table_args__ = (
        Index("idx_event_logs_occurred", "occurred_at", "id"),
        Index("idx_event_logs_correlation", "correlation_id", "occurred_at"),
        Index("idx_event_logs_strategy_run", "strategy_run_id", "occurred_at"),
        Index("idx_event_logs_order", "order_id", "occurred_at"),
        Index("idx_event_logs_symbol", "symbol", "occurred_at"),
        {"comment": "统一事件日志表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="事件日志主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, comment="用户 ID")
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), index=True, nullable=True, comment="账户 ID")
    event_type: Mapped[EventLogType] = mapped_column(Enum(EventLogType), index=True, comment="事件类型")
    symbol: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True, comment="标的代码")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True, comment="发生时间")
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), index=True, nullable=True, comment="策略 ID")
    strategy_run_id: Mapped[int | None] = mapped_column(ForeignKey("strategy_runs.id"), index=True, nullable=True, comment="策略运行 ID")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True, nullable=True, comment="订单 ID")
    order_event_id: Mapped[int | None] = mapped_column(ForeignKey("order_events.id"), index=True, nullable=True, comment="订单事件 ID")
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), index=True, nullable=True, comment="成交 ID")
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), index=True, nullable=True, comment="持仓 ID")
    equity_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("equity_snapshots.id"), index=True, nullable=True, comment="权益快照 ID")
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True, comment="事件链路关联 ID")
    risk_rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="风控规则版本")
    payload: Mapped[dict] = mapped_column(JSON, default=dict, comment="事件载荷")
