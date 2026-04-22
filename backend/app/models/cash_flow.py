from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class CashFlowType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    TRADE = "trade"
    FEE = "fee"
    SETTLEMENT = "settlement"


class CashFlow(Base):
    __tablename__ = "cash_flows"
    __table_args__ = {"comment": "资金流水表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="流水主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True, comment="关联账户 ID")
    flow_type: Mapped[CashFlowType] = mapped_column(Enum(CashFlowType), comment="流水类型")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), comment="流水金额")
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="流水后余额")
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="业务引用")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    account = relationship("Account", back_populates="cash_flows")
