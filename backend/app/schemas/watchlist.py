from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WatchlistCreate(BaseModel):
    symbol: str
    group_id: int | None = None
    note: str | None = None


class WatchlistRead(BaseModel):
    id: int
    tenant_id: str
    symbol: str
    group_id: int | None
    sort_order: int
    note: str | None
    is_pinned: bool
    is_special_attention: bool
    security_name: str
    security_code: str
    market: str
    tags: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WatchlistUpdate(BaseModel):
    group_id: int | None = None
    note: str | None = None
    is_pinned: bool | None = None
    is_special_attention: bool | None = None


class WatchlistReorderPayload(BaseModel):
    group_id: int
    pinned_ids: list[int]
    regular_ids: list[int]


class WatchlistGroupCreate(BaseModel):
    name: str


class WatchlistGroupUpdate(BaseModel):
    name: str | None = None


class WatchlistGroupReorderPayload(BaseModel):
    group_ids: list[int]


class WatchlistGroupRead(BaseModel):
    id: int
    tenant_id: str
    name: str
    is_system: bool
    sort_order: int
    item_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
