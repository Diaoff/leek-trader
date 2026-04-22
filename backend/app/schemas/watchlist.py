from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WatchlistCreate(BaseModel):
    symbol: str


class WatchlistRead(BaseModel):
    id: int
    tenant_id: str
    symbol: str
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
