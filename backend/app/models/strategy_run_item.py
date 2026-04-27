from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class StrategyRunItem(Base):
    __tablename__ = "strategy_run_items"
    __table_args__ = {"comment": "策略逐标的运行结果表"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="运行结果项主键 ID")
    run_id: Mapped[int] = mapped_column(ForeignKey("strategy_runs.id", ondelete="CASCADE"), index=True, comment="关联运行 ID")
    symbol: Mapped[str] = mapped_column(String(32), index=True, comment="执行标的")
    signal: Mapped[dict] = mapped_column(JSON, default=dict, comment="逐标的策略信号快照")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
