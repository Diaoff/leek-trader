from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class WatchlistGroup(Base):
    __tablename__ = "watchlist_groups"
    __table_args__ = (
        Index("idx_watchlist_group_user_name", "user_id", "name", unique=True),
        Index("idx_watchlist_group_user_sort_order", "user_id", "sort_order"),
        {"comment": "自选股分组"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="分组主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, comment="用户 ID")
    name: Mapped[str] = mapped_column(String(64), comment="分组名称")
    is_system: Mapped[bool] = mapped_column(default=False, comment="是否系统内置分组")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序值")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
