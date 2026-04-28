from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class StrategyRunStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrategyRun(Base):
    __tablename__ = "strategy_runs"
    __table_args__ = {"comment": "策略运行记录表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="策略运行主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True, comment="关联策略 ID")
    status: Mapped[StrategyRunStatus] = mapped_column(Enum(StrategyRunStatus), default=StrategyRunStatus.PENDING, comment="运行状态")
    signal: Mapped[dict] = mapped_column(JSON, default=dict, comment="策略信号快照")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, comment="更新时间")
