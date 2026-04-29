from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    symbol: str
    side: Literal['buy', 'sell']
    order_type: Literal['market', 'limit']
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0)


class OrderRead(BaseModel):
    id: int
    tenant_id: str
    account_id: int
    symbol: str
    name: str | None = None
    side: Literal['buy', 'sell']
    order_type: Literal['market', 'limit']
    status: Literal['pending', 'filled', 'rejected', 'cancelled']
    quantity: int
    price: Decimal
    filled_quantity: int
    filled_price: Decimal
    reject_reason: str | None

    model_config = ConfigDict(from_attributes=True)
