from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        Index("idx_watchlist_user_symbol", "user_id", "symbol", unique=True),
        Index("idx_watchlist_user_sort_order", "user_id", "sort_order"),
        {"comment": "自选股列表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="自选项主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, comment="用户 ID")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="证券代码")
    group_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True, comment="所属分组 ID")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序值")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="自定义备注")
    is_pinned: Mapped[bool] = mapped_column(default=False, comment="是否固定置顶")
    is_special_attention: Mapped[bool] = mapped_column(default=False, comment="是否特别关注")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
