from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        Index("idx_watchlist_tenant_symbol", "tenant_id", "symbol", unique=True),
        Index("idx_watchlist_tenant_sort_order", "tenant_id", "sort_order"),
        {"comment": "自选股列表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="自选项主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="证券代码")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序值")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
