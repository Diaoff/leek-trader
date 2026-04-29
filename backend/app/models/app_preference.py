from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AppPreference(Base):
    __tablename__ = "app_preferences"
    __table_args__ = {"comment": "应用偏好设置表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="偏好主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="租户 ID")
    trading_preferences: Mapped[dict] = mapped_column(JSON, default=dict, comment="交易偏好 JSON")
    strategy_scheduler_preferences: Mapped[dict] = mapped_column(JSON, default=dict, comment="策略调度偏好 JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
