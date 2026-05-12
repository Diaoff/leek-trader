from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (
        Index("idx_strategy_versions_strategy_version", "strategy_id", "version"),
        {"comment": "策略参数版本快照表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="版本快照主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, comment="用户 ID")
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True, comment="策略 ID")
    version: Mapped[int] = mapped_column(Integer, comment="策略版本号")
    name: Mapped[str] = mapped_column(String(128), comment="策略名称快照")
    symbol: Mapped[str] = mapped_column(String(32), default="", comment="标的快照")
    strategy_type: Mapped[str] = mapped_column(String(32), comment="策略类型快照")
    execution_mode: Mapped[str] = mapped_column(String(32), comment="执行模式快照")
    target_type: Mapped[str] = mapped_column(String(32), comment="目标类型快照")
    target_config: Mapped[dict] = mapped_column(JSON, default=dict, comment="目标配置快照")
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, comment="参数快照")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")

    strategy = relationship("Strategy")
