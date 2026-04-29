from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class SmartSelectionInstitutionPoolItem(Base):
    __tablename__ = "smart_selection_institution_pool_items"
    __table_args__ = {"comment": "智能选股券商推荐池快照表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="券商推荐池明细主键 ID")
    run_id: Mapped[int] = mapped_column(ForeignKey("smart_selection_runs.id", ondelete="CASCADE"), index=True, comment="智能选股运行 ID")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="证券 symbol")
    code: Mapped[str] = mapped_column(String(16), index=True, comment="证券代码")
    name: Mapped[str] = mapped_column(String(64), comment="证券名称")
    rating_date: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True, comment="评级日期")
    rating: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="券商评级")
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="目标价")
    latest_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="最新价")
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="涨跌幅")
    recommend_count: Mapped[int] = mapped_column(Integer, default=1, index=True, comment="聚合推荐次数")
    institutions: Mapped[list] = mapped_column(JSON, default=list, comment="推荐机构列表")
    industries: Mapped[list] = mapped_column(JSON, default=list, comment="行业列表")
    raw_detail: Mapped[dict] = mapped_column(JSON, default=dict, comment="原始券商推荐明细")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
