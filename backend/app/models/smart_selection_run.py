from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class SmartSelectionRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SmartSelectionRun(Base):
    __tablename__ = "smart_selection_runs"
    __table_args__ = {"comment": "智能选股运行记录表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="运行主键 ID")
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, default="local", comment="租户 ID")
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, comment="关联 Celery 任务 ID")
    status: Mapped[SmartSelectionRunStatus] = mapped_column(
        Enum(SmartSelectionRunStatus),
        default=SmartSelectionRunStatus.QUEUED,
        index=True,
        comment="运行状态",
    )
    triggered_by: Mapped[str] = mapped_column(String(32), default="system", comment="触发方式")
    candidate_pool_size: Mapped[int] = mapped_column(Integer, default=0, comment="候选池规模")
    recommendation_count: Mapped[int] = mapped_column(Integer, default=0, comment="最终推荐数量")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="摘要")
    report_body: Mapped[str | None] = mapped_column(Text, nullable=True, comment="报告正文")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败错误")
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, comment="运行时配置快照")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="报告生成时间")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="结束时间")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
