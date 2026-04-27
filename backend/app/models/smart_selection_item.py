from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class SmartSelectionItem(Base):
    __tablename__ = "smart_selection_items"
    __table_args__ = {"comment": "智能选股推荐明细表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="推荐明细主键 ID")
    run_id: Mapped[int] = mapped_column(ForeignKey("smart_selection_runs.id", ondelete="CASCADE"), index=True, comment="运行 ID")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="证券 symbol")
    code: Mapped[str] = mapped_column(String(16), index=True, comment="证券代码")
    name: Mapped[str] = mapped_column(String(64), comment="证券名称")
    score: Mapped[float] = mapped_column(Float, default=0.0, comment="综合评分")
    price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="当前价格")
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="涨跌幅")
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="目标价")
    stop_loss_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="止损价")
    tags: Mapped[list] = mapped_column(JSON, default=list, comment="标签")
    reason: Mapped[str] = mapped_column(Text, default="", comment="推荐理由")
    dimension_scores: Mapped[dict] = mapped_column(JSON, default=dict, comment="维度评分拆解")
    raw_detail: Mapped[dict] = mapped_column(JSON, default=dict, comment="原始分析明细")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
