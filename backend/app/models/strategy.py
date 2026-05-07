from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class StrategyType(StrEnum):
    MOVING_AVERAGE = "moving_average"
    MACD = "macd"
    RL_TRADING = "rl_trading"


class StrategyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class StrategyExecutionMode(StrEnum):
    SIGNAL_ONLY = "signal_only"
    AUTO_TRADE = "auto_trade"


class StrategyTargetType(StrEnum):
    SINGLE_SYMBOL = "single_symbol"
    SPECIAL_ATTENTION = "special_attention"


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_cls]


def utc_now() -> datetime:
    return datetime.now(UTC)


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = {"comment": "策略定义表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="策略主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, comment="用户 ID")
    name: Mapped[str] = mapped_column(String(128), comment="策略名称")
    symbol: Mapped[str] = mapped_column(String(32), default="", comment="兼容字段：单标的策略标的")
    strategy_type: Mapped[StrategyType] = mapped_column(
        Enum(
            StrategyType,
            values_callable=_enum_values,
        ),
        comment="策略类型",
    )
    status: Mapped[StrategyStatus] = mapped_column(
        Enum(
            StrategyStatus,
            values_callable=_enum_values,
        ),
        default=StrategyStatus.DRAFT,
        comment="策略状态",
    )
    target_type: Mapped[StrategyTargetType] = mapped_column(
        Enum(
            StrategyTargetType,
            values_callable=_enum_values,
            native_enum=False,
        ),
        default=StrategyTargetType.SINGLE_SYMBOL,
        comment="策略目标范围类型",
    )
    target_config: Mapped[dict] = mapped_column(JSON, default=dict, comment="策略目标范围配置")
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, comment="更新时间")
