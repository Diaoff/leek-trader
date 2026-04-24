from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"
    __table_args__ = {"comment": "规则研究快照推荐明细表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="推荐明细主键 ID")
    run_id: Mapped[int] = mapped_column(ForeignKey("recommendation_runs.id", ondelete="CASCADE"), index=True, comment="关联快照运行 ID")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="证券 symbol")
    code: Mapped[str] = mapped_column(String(16), index=True, comment="证券代码")
    name: Mapped[str] = mapped_column(String(64), comment="证券名称")
    security_type: Mapped[str] = mapped_column(String(16), default="stock", comment="证券类型")
    risk: Mapped[str] = mapped_column(String(16), default="medium", comment="风险分层")
    score: Mapped[float] = mapped_column(Float, default=0.0, comment="规则评分")
    strategy: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="策略类型")
    layer: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="推荐分层")
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="所属板块")
    sector_rank: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="板块排名")
    price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="参考价格")
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="涨跌幅")
    reasons: Mapped[list] = mapped_column(JSON, default=list, comment="推荐理由列表")
    support_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="支撑类型")
    support_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="支撑位")
    support_distance_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="距支撑位百分比")
    atr_stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True, comment="ATR 止损价")
    previous_recommendation_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="上次推荐价格")
    previous_recommendation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="上次推荐时间")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
