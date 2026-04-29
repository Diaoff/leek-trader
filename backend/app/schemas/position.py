from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PositionRead(BaseModel):
    id: int
    tenant_id: str
    account_id: int
    symbol: str
    name: str | None = None
    market: str
    quantity: int
    available_quantity: int
    average_cost: Decimal
    last_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    strategy_add_count: int
    exit_guard_status: str
    exit_trigger_reason: str | None
    exit_triggered_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
