from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        Index("idx_positions_account_symbol", "account_id", "symbol", unique=True),
        Index("idx_positions_last_price", "last_price"),
        Index("idx_positions_last_buy_date", "last_buy_date"),
        Index("idx_positions_unrealized_pnl", "unrealized_pnl"),
        {"comment": "账户持仓表"}
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="持仓主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True, comment="关联账户 ID")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="证券代码")
    market: Mapped[str] = mapped_column(String(16), default="CN", comment="市场标识")
    quantity: Mapped[int] = mapped_column(Integer, default=0, comment="持仓数量")
    available_quantity: Mapped[int] = mapped_column(Integer, default=0, comment="可卖数量")
    frozen_quantity: Mapped[int] = mapped_column(Integer, default=0, comment="冻结数量")
    average_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, comment="持仓成本价")
    last_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, comment="最新价")
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="浮动盈亏")
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="已实现盈亏")
    last_buy_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="最近买入日期")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    account = relationship("Account", back_populates="positions")
