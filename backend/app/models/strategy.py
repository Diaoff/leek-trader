from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class StrategyType(StrEnum):
    MOVING_AVERAGE = "moving_average"
    MACD = "macd"


class StrategyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class StrategyExecutionMode(StrEnum):
    SIGNAL_ONLY = "signal_only"
    AUTO_TRADE = "auto_trade"


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_cls]


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = {"comment": "策略定义表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="策略主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    name: Mapped[str] = mapped_column(String(128), comment="策略名称")
    symbol: Mapped[str] = mapped_column(String(32), default="sh600519", comment="策略标的")
    strategy_type: Mapped[StrategyType] = mapped_column(Enum(StrategyType), comment="策略类型")
    status: Mapped[StrategyStatus] = mapped_column(Enum(StrategyStatus), default=StrategyStatus.DRAFT, comment="策略状态")
    execution_mode: Mapped[StrategyExecutionMode] = mapped_column(
        Enum(
            StrategyExecutionMode,
            values_callable=_enum_values,
            native_enum=False,
        ),
        default=StrategyExecutionMode.SIGNAL_ONLY,
        comment="执行模式",
    )
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, comment="策略参数")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
