from pydantic import BaseModel


class ReportingSummary(BaseModel):
    trade_count: int
    realized_pnl: float
    win_rate: float
    cumulative_return: float
    profit_factor: float
    max_drawdown: float
    avg_win: float
    avg_loss: float
    annualized_return_pct: float | None = None
    annualized_volatility_pct: float | None = None
    sharpe_ratio: float | None = None
    calmar_ratio: float | None = None


class EquityCurvePoint(BaseModel):
    label: str
    total_equity: float


class PeriodStat(BaseModel):
    period: str
    trade_count: int
    realized_pnl: float
    ending_equity: float
