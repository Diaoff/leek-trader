from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class AccountStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = {"comment": "模拟交易账户表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="账户主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), comment="用户 ID")
    name: Mapped[str] = mapped_column(String(128), default="模拟账户", comment="账户名称")
    currency: Mapped[str] = mapped_column(String(16), default="CNY", comment="账户币种")
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="初始资金")
    available_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="可用资金")
    frozen_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="冻结资金")
    total_equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="账户总权益")
    status: Mapped[AccountStatus] = mapped_column(Enum(AccountStatus), default=AccountStatus.ACTIVE, comment="账户状态")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    user = relationship("User", back_populates="accounts")
    positions = relationship("Position", back_populates="account")
    orders = relationship("Order", back_populates="account")
    trades = relationship("Trade", back_populates="account")
    cash_flows = relationship("CashFlow", back_populates="account")
