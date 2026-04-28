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
        Index("idx_positions_exit_guard_status", "exit_guard_status"),
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
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True, comment="持仓级止损价")
    take_profit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True, comment="持仓级止盈价")
    strategy_add_count: Mapped[int] = mapped_column(Integer, default=0, comment="当前持仓生命周期内策略补仓次数")
    exit_guard_status: Mapped[str] = mapped_column(String(32), default="inactive", comment="持仓保护状态")
    exit_trigger_reason: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="最近一次保护触发原因")
    exit_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="最近一次保护触发时间")
    last_buy_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="最近买入日期")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    account = relationship("Account", back_populates="positions")
