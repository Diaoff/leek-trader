from pydantic import BaseModel


class QuoteRead(BaseModel):
    symbol: str
    name: str | None = None
    price: float
    change_percent: float
    volume: float
    timestamp: str
    is_halted: bool
    market_cap: float | None = None
    ytd_change_percent: float | None = None
