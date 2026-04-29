from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


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

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, value):
        return getattr(value, "value", value)
