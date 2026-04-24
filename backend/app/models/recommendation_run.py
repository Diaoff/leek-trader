from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class RecommendationRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"
    __table_args__ = {"comment": "规则研究快照头信息表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="快照运行主键 ID")
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, comment="关联 Celery 任务 ID")
    status: Mapped[RecommendationRunStatus] = mapped_column(
        Enum(RecommendationRunStatus),
        default=RecommendationRunStatus.QUEUED,
        index=True,
        comment="研究任务状态",
    )
    triggered_by: Mapped[str] = mapped_column(String(32), default="system", comment="触发方式")
    candidate_pool_size: Mapped[int] = mapped_column(Integer, default=0, comment="候选池规模")
    recommendation_count: Mapped[int] = mapped_column(Integer, default=0, comment="最终推荐数量")
    northbound_net_inflow: Mapped[float | None] = mapped_column(Float, nullable=True, comment="北向净流入")
    market_sentiment: Mapped[dict] = mapped_column(JSON, default=dict, comment="市场情绪快照")
    sector_momentum_top: Mapped[list] = mapped_column(JSON, default=list, comment="板块动量前排")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="研究结论摘要")
    report_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="报告摘要文本")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="任务失败错误")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="快照生成时间")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="任务开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="任务结束时间")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
