from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


ORDER_ALLOWED_TRANSITIONS: dict[OrderStatus | None, set[OrderStatus]] = {
    None: {OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.REJECTED},
    OrderStatus.PENDING: {OrderStatus.ACCEPTED, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.REJECTED},
    OrderStatus.ACCEPTED: {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.FILLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.EXPIRED: set(),
}


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("idx_orders_account_status", "account_id", "status"),
        Index("idx_orders_account_side", "account_id", "side"),
        Index("idx_orders_created_at", "created_at"),
        {"comment": "交易委托单表"}
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="订单主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True, comment="关联账户 ID")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="证券代码")
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide), comment="买卖方向")
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), default=OrderType.MARKET, comment="订单类型")
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.PENDING, comment="订单状态")
    quantity: Mapped[int] = mapped_column(Integer, comment="委托数量")
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, comment="委托价格")
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0, comment="成交数量")
    filled_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, comment="成交价格")
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="拒单原因")
    risk_rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="风控规则版本")
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True, comment="事件链路关联 ID")
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), index=True, nullable=True, comment="关联策略 ID")
    strategy_run_id: Mapped[int | None] = mapped_column(ForeignKey("strategy_runs.id"), index=True, nullable=True, comment="关联策略运行 ID")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    account = relationship("Account", back_populates="orders")
    trades = relationship("Trade", back_populates="order")
    events = relationship("OrderEvent", back_populates="order", order_by="OrderEvent.created_at")

    @classmethod
    def can_transition(cls, from_status: OrderStatus | None, to_status: OrderStatus) -> bool:
        return to_status in ORDER_ALLOWED_TRANSITIONS.get(from_status, set())

    def transition_to(self, to_status: OrderStatus) -> OrderStatus | None:
        from_status = self.status
        if from_status == to_status:
            return from_status
        if not self.can_transition(from_status, to_status):
            raise ValueError(f"illegal order status transition: {from_status.value} -> {to_status.value}")
        self.status = to_status
        return from_status
