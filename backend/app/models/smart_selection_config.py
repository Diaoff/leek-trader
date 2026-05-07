from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class SmartSelectionConfig(Base):
    __tablename__ = "smart_selection_configs"
    __table_args__ = (
        Index("idx_smart_selection_config_user", "user_id", unique=True),
        {"comment": "智能选股用户配置表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="配置主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, comment="租户 ID")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, comment="用户 ID")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用日常调度")
    schedule_time: Mapped[str] = mapped_column(String(16), default="20:00", comment="固定执行时间展示值")
    config_payload: Mapped[dict] = mapped_column(JSON, default=dict, comment="完整参考配置 JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
