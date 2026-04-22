from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"
    __table_args__ = (
        Index("idx_equity_account_recorded", "account_id", "recorded_at"),
        {"comment": "账户权益快照"}
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户 ID")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True, comment="账户 ID")
    total_equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="账户总权益")
    available_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="可用资金")
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="持仓市值")
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="浮动盈亏")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True, comment="记录时间")

    account = relationship("Account")
