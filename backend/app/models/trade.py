from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("idx_trades_account_executed", "account_id", "executed_at"),
        Index("idx_trades_symbol_executed", "symbol", "executed_at"),
        Index("idx_trades_executed_at", "executed_at"),
        {"comment": "成交记录表"}
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="成交主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True, comment="关联账户 ID")
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, comment="关联订单 ID")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="证券代码")
    quantity: Mapped[int] = mapped_column(Integer, comment="成交数量")
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), comment="成交价格")
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="手续费")
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="已实现盈亏")
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="成交时间")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    account = relationship("Account", back_populates="trades")
    order = relationship("Order", back_populates="trades")
