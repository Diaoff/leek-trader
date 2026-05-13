from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AiConfig(Base):
    __tablename__ = "ai_configs"
    __table_args__ = (
        Index("idx_ai_config_user", "user_id", unique=True),
        {"comment": "AI 模型配置"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="AI 配置主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, comment="用户 ID")
    provider: Mapped[str] = mapped_column(String(32), default="openai_compatible", comment="模型提供商")
    base_url: Mapped[str] = mapped_column(String(255), default="", comment="大模型基础地址")
    api_key: Mapped[str] = mapped_column(Text, default="", comment="大模型 API Key")
    model: Mapped[str] = mapped_column(String(128), default="", comment="大模型名称")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
