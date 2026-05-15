from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.order import OrderStatus


class OrderEventType(StrEnum):
    CREATED = "created"
    RISK_CHECK = "risk_check"
    ACCEPTED = "accepted"
    PARTIAL_FILL = "partial_fill"
    FILL = "fill"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (
        Index("idx_order_events_order_created", "order_id", "created_at"),
        Index("idx_order_events_correlation", "correlation_id", "created_at"),
        {"comment": "订单状态与风控事件表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="订单事件主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True, comment="关联账户 ID")
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, comment="关联订单 ID")
    event_type: Mapped[OrderEventType] = mapped_column(Enum(OrderEventType), comment="订单事件类型")
    from_status: Mapped[OrderStatus | None] = mapped_column(Enum(OrderStatus), nullable=True, comment="事件前订单状态")
    to_status: Mapped[OrderStatus | None] = mapped_column(Enum(OrderStatus), nullable=True, comment="事件后订单状态")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="事件原因")
    risk_rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="风控规则版本")
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True, comment="事件链路关联 ID")
    payload: Mapped[dict] = mapped_column(JSON, default=dict, comment="扩展事件载荷")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="事件时间")

    order = relationship("Order", back_populates="events")
