from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AccountBase(BaseModel):
    tenant_id: str
    name: str
    currency: str
    status: Literal['active', 'paused']


class AccountRead(AccountBase):
    id: int
    initial_cash: Decimal
    available_cash: Decimal
    frozen_cash: Decimal
    total_equity: Decimal

    model_config = ConfigDict(from_attributes=True)
