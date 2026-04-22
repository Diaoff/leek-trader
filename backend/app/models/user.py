from datetime import datetime
from sqlalchemy import DateTime, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class User(Base):
    """用户模型"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, comment="用户ID")
    tenant_id: Mapped[str] = mapped_column(String(50), index=True, comment="租户ID")
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False, comment="用户名")
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False, comment="邮箱")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="姓名")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否激活")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否超级用户")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关系
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
