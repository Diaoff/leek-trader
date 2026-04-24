from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AsyncTaskExecutionStatus(StrEnum):
    STARTED = "started"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AsyncTaskExecution(Base):
    __tablename__ = "async_task_executions"
    __table_args__ = {"comment": "异步任务执行记录表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="异步任务执行主键 ID")
    task_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, comment="Celery 任务 ID")
    task_name: Mapped[str] = mapped_column(String(255), index=True, comment="Celery 任务名")
    status: Mapped[AsyncTaskExecutionStatus] = mapped_column(
        Enum(AsyncTaskExecutionStatus),
        default=AsyncTaskExecutionStatus.STARTED,
        comment="任务当前状态",
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="任务累计重试次数")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="最近一次失败错误")
    last_retry_error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="最近一次重试错误")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="开始时间")
    last_retried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="最近一次重试时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="结束时间")
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="最近一次事件时间")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
