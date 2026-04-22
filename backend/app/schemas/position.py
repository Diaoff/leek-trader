from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PositionRead(BaseModel):
    id: int
    tenant_id: str
    account_id: int
    symbol: str
    market: str
    quantity: int
    available_quantity: int
    average_cost: Decimal
    last_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal

    model_config = ConfigDict(from_attributes=True)
