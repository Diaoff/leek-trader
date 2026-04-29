from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class MarketDailyBar(Base):
    __tablename__ = "market_daily_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", "source", "adjustflag", name="uq_market_daily_bars_symbol_date_source_adjustflag"),
        {"comment": "离线历史日线行情表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="历史日线主键 ID")
    symbol: Mapped[str] = mapped_column(String(16), index=True, comment="标准化 A 股代码，如 sh600000")
    trade_date: Mapped[date] = mapped_column(Date, index=True, comment="交易日期")
    source: Mapped[str] = mapped_column(String(32), default="baostock", index=True, comment="历史数据源")
    adjustflag: Mapped[str] = mapped_column(String(8), default="2", index=True, comment="复权口径，BaoStock 2 表示前复权")
    open_price: Mapped[float] = mapped_column(Float, comment="开盘价")
    close_price: Mapped[float] = mapped_column(Float, comment="收盘价")
    high_price: Mapped[float] = mapped_column(Float, comment="最高价")
    low_price: Mapped[float] = mapped_column(Float, comment="最低价")
    volume: Mapped[float] = mapped_column(Float, default=0.0, comment="成交量")
    turnover: Mapped[float] = mapped_column(Float, default=0.0, comment="成交额")
    amplitude_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="振幅百分比")
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True, comment="涨跌幅百分比")
    turnover_rate: Mapped[float | None] = mapped_column(Float, nullable=True, comment="换手率")
    preclose: Mapped[float | None] = mapped_column(Float, nullable=True, comment="前收盘价")
    trade_status: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="交易状态，1 为交易，0 为停牌")
    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True, comment="滚动市盈率")
    pb_mrq: Mapped[float | None] = mapped_column(Float, nullable=True, comment="市净率")
    ps_ttm: Mapped[float | None] = mapped_column(Float, nullable=True, comment="滚动市销率")
    pcf_ncf_ttm: Mapped[float | None] = mapped_column(Float, nullable=True, comment="滚动市现率")
    is_st: Mapped[bool | None] = mapped_column(Boolean, nullable=True, comment="是否 ST")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )
