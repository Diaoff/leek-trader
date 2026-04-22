from pydantic import BaseModel


class QuoteRead(BaseModel):
    symbol: str
    price: float
    change_percent: float
    volume: float
    timestamp: str
    is_halted: bool
