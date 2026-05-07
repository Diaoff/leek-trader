from datetime import datetime

from sqlalchemy import DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class MarketIntradayBar(Base):
    __tablename__ = "market_intraday_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "bar_time", "source", name="uq_market_intraday_bars_symbol_interval_time_source"),
        {"comment": "分钟级分时 K 线行情表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="分钟 K 主键 ID")
    symbol: Mapped[str] = mapped_column(String(16), index=True, comment="标准化 A 股代码，如 sh600000")
    bar_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, comment="分钟 K 结束时间")
    interval: Mapped[str] = mapped_column(String(8), index=True, comment="分钟周期，如 5m/15m")
    source: Mapped[str] = mapped_column(String(32), default="eastmoney", index=True, comment="分钟数据源")
    open_price: Mapped[float] = mapped_column(Float, comment="开盘价")
    high_price: Mapped[float] = mapped_column(Float, comment="最高价")
    low_price: Mapped[float] = mapped_column(Float, comment="最低价")
    close_price: Mapped[float] = mapped_column(Float, comment="收盘价")
    volume: Mapped[float] = mapped_column(Float, default=0.0, comment="成交量")
    turnover: Mapped[float] = mapped_column(Float, default=0.0, comment="成交额")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
