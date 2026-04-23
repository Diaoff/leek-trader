from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.schemas.watchlist import (
    WatchlistGroupCreate,
    WatchlistGroupRead,
    WatchlistGroupReorderPayload,
    WatchlistGroupUpdate,
)
from app.watchlist.service import WatchlistService

router = APIRouter(prefix="/watchlist-groups")
service = WatchlistService()


@router.get("", response_model=list[WatchlistGroupRead])
def list_watchlist_groups(db: Session = Depends(get_db)) -> list[WatchlistGroupRead]:
    return service.list_groups(db, settings.default_tenant_id)


@router.post("", response_model=WatchlistGroupRead)
def create_watchlist_group(payload: WatchlistGroupCreate, db: Session = Depends(get_db)) -> WatchlistGroupRead:
    return service.create_group(db, settings.default_tenant_id, payload.name)


@router.patch("/{group_id}", response_model=WatchlistGroupRead)
def update_watchlist_group(
    group_id: int,
    payload: WatchlistGroupUpdate,
    db: Session = Depends(get_db),
) -> WatchlistGroupRead:
    return service.update_group(db, settings.default_tenant_id, group_id, payload.name)


@router.post("/reorder")
def reorder_watchlist_groups(payload: WatchlistGroupReorderPayload, db: Session = Depends(get_db)) -> dict[str, str]:
    service.reorder_groups(db, settings.default_tenant_id, payload.group_ids)
    return {"status": "ok"}


@router.delete("/{group_id}")
def delete_watchlist_group(group_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    service.delete_group(db, settings.default_tenant_id, group_id)
    return {"status": "deleted", "id": group_id}
