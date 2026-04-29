from __future__ import annotations

from math import log1p
from typing import Any

from app.market.providers.base import DailyBarSnapshot

RL_DATASET_FIELDS = [
    "symbol",
    "trade_date",
    "open_price",
    "close_price",
    "high_price",
    "low_price",
    "volume",
    "turnover",
    "amplitude_pct",
    "change_pct",
    "turnover_rate",
    "preclose",
    "trade_status",
    "pe_ttm",
    "pb_mrq",
    "ps_ttm",
    "pcf_ncf_ttm",
    "is_st",
]

RL_DATASET_SCHEMA_VERSION = "rl-daily-bars/v1"

RL_FEATURE_DESCRIPTIONS = {
    "symbol": "标准化 A 股代码，如 sh600000",
    "trade_date": "交易日期",
    "open_price": "开盘价",
    "close_price": "收盘价",
    "high_price": "最高价",
    "low_price": "最低价",
    "volume": "成交量",
    "turnover": "成交额",
    "amplitude_pct": "振幅百分比；BaoStock 当前可能为空",
    "change_pct": "涨跌幅百分比",
    "turnover_rate": "换手率",
    "preclose": "前收盘价",
    "trade_status": "交易状态，1 为交易，0 为停牌",
    "pe_ttm": "滚动市盈率",
    "pb_mrq": "市净率",
    "ps_ttm": "滚动市销率",
    "pcf_ncf_ttm": "滚动市现率",
    "is_st": "是否 ST；底座保留但默认不剔除",
}
RL_PRICE_FIELDS = ["open_price", "close_price", "high_price", "low_price", "preclose"]
RL_LIQUIDITY_FIELDS = ["volume", "turnover", "turnover_rate"]
RL_FACTOR_FIELDS = ["change_pct", "amplitude_pct", "pe_ttm", "pb_mrq", "ps_ttm", "pcf_ncf_ttm", "is_st", "trade_status"]
RL_NULLABLE_FIELDS = ["amplitude_pct", "change_pct", "turnover_rate", "preclose", "trade_status", "pe_ttm", "pb_mrq", "ps_ttm", "pcf_ncf_ttm", "is_st"]


def daily_bar_to_rl_record(bar: DailyBarSnapshot) -> dict[str, Any]:
    return {
        "symbol": bar.symbol,
        "trade_date": bar.trade_date.isoformat(),
        "open_price": bar.open_price,
        "close_price": bar.close_price,
        "high_price": bar.high_price,
        "low_price": bar.low_price,
        "volume": bar.volume,
        "turnover": bar.turnover,
        "amplitude_pct": bar.amplitude_pct,
        "change_pct": bar.change_pct,
        "turnover_rate": bar.turnover_rate,
        "preclose": bar.preclose,
        "trade_status": bar.trade_status,
        "pe_ttm": bar.pe_ttm,
        "pb_mrq": bar.pb_mrq,
        "ps_ttm": bar.ps_ttm,
        "pcf_ncf_ttm": bar.pcf_ncf_ttm,
        "is_st": bar.is_st,
    }


def build_rl_state(bars: list[DailyBarSnapshot], *, short_window: int, long_window: int) -> dict[str, Any]:
    closes = [float(bar.close_price) for bar in bars]
    latest = closes[-1]
    previous = closes[-2]
    short_average = sum(closes[-short_window:]) / short_window
    long_average = sum(closes[-long_window:]) / long_window
    returns = [0.0 if closes[index - 1] <= 0 else (closes[index] - closes[index - 1]) / closes[index - 1] for index in range(1, len(closes))]
    recent_returns = returns[-min(20, len(returns)) :]
    mean_return = sum(recent_returns) / len(recent_returns) if recent_returns else 0.0
    variance = sum((item - mean_return) ** 2 for item in recent_returns) / len(recent_returns) if recent_returns else 0.0
    volatility_pct = variance**0.5 * 100
    latest_volume = float(bars[-1].volume or 0.0)
    volume_window = bars[-min(20, len(bars)) :]
    average_volume = sum(float(bar.volume or 0.0) for bar in volume_window) / len(volume_window)
    trend_strength = (short_average - long_average) / long_average if long_average else 0.0
    market_regime = "bullish" if latest > short_average > long_average else "bearish" if latest < short_average < long_average else "neutral"
    return {
        "close_price": round(latest, 6),
        "previous_close_price": round(previous, 6),
        "return_1d": round((latest - previous) / previous, 8) if previous else 0.0,
        "ma_short": round(short_average, 6),
        "ma_long": round(long_average, 6),
        "price_ma_short_ratio": round(latest / short_average, 8) if short_average else 0.0,
        "price_ma_long_ratio": round(latest / long_average, 8) if long_average else 0.0,
        "trend_strength": round(trend_strength, 8),
        "volatility_pct": round(volatility_pct, 6),
        "volume_log1p": round(log1p(max(latest_volume, 0.0)), 6),
        "volume_ratio": round(latest_volume / average_volume, 8) if average_volume else 0.0,
        "pe_ttm": bars[-1].pe_ttm,
        "pb_mrq": bars[-1].pb_mrq,
        "ps_ttm": bars[-1].ps_ttm,
        "pcf_ncf_ttm": bars[-1].pcf_ncf_ttm,
        "market_regime": market_regime,
    }


def normalization_hints() -> dict[str, str]:
    return {
        "price": "建议按前收盘、首日收盘或 rolling window 做相对化，避免绝对价格尺度主导训练。",
        "volume_turnover": "建议对 volume/turnover 使用 log1p 或 rolling z-score，降低量纲和极端值影响。",
        "valuation": "建议对估值字段 winsorize 后 z-score，保留异常但降低尾部冲击。",
        "boolean_status": "建议保留 trade_status/is_st 的原始 0/1/null 语义，交由训练侧处理缺失。",
    }
