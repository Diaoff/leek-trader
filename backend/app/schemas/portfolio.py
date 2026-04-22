from pydantic import BaseModel


class PortfolioSummary(BaseModel):
    total_equity: float
    available_cash: float
    frozen_cash: float
    market_value: float
    unrealized_pnl: float
