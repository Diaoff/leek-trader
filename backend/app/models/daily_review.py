from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, JSON, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class DailyReview(Base):
    __tablename__ = "daily_reviews"
    __table_args__ = (
        Index("idx_daily_reviews_user_date", "user_id", "review_date"),
        Index("idx_daily_reviews_symbol_date", "symbol", "review_date"),
        {"comment": "本地历史复盘归档表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="复盘归档主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, default="local", comment="租户标识")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True, comment="用户 ID")
    review_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True, comment="复盘日期")
    symbol: Mapped[str] = mapped_column(String(32), index=True, default="", comment="证券代码")
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), index=True, nullable=True, comment="策略 ID")
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="策略名称")
    strategy_type: Mapped[str] = mapped_column(String(32), default="", comment="策略类型")
    headline: Mapped[str] = mapped_column(String(255), comment="复盘标题")
    highlights: Mapped[list] = mapped_column(JSON, default=list, comment="亮点")
    risks: Mapped[list] = mapped_column(JSON, default=list, comment="风险")
    next_actions: Mapped[list] = mapped_column(JSON, default=list, comment="下一步建议")
    backtest_summary: Mapped[dict] = mapped_column(JSON, default=dict, comment="回测摘要")
    payload: Mapped[dict] = mapped_column(JSON, default=dict, comment="完整复盘载荷")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    strategy = relationship("Strategy")
