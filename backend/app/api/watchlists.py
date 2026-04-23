from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.schemas.watchlist import WatchlistCreate, WatchlistRead, WatchlistReorderPayload, WatchlistUpdate
from app.watchlist.service import WatchlistService

router = APIRouter(prefix="/watchlists")
service = WatchlistService()


@router.get("", response_model=list[WatchlistRead])
def list_watchlists(group_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> list[WatchlistRead]:
    return service.list_items(db, settings.default_tenant_id, group_id)


@router.post("", response_model=WatchlistRead)
def create_watchlist(payload: WatchlistCreate, db: Session = Depends(get_db)) -> WatchlistRead:
    return service.create_item(db, settings.default_tenant_id, payload)


@router.patch("/{item_id}", response_model=WatchlistRead)
def update_watchlist(item_id: int, payload: WatchlistUpdate, db: Session = Depends(get_db)) -> WatchlistRead:
    return service.update_item(db, settings.default_tenant_id, item_id, payload)


@router.post("/reorder")
def reorder_watchlists(payload: WatchlistReorderPayload, db: Session = Depends(get_db)) -> dict[str, str]:
    service.reorder_items(
        db,
        settings.default_tenant_id,
        payload.group_id,
        payload.pinned_ids,
        payload.regular_ids,
    )
    return {"status": "ok"}


@router.delete("/{item_id}")
def delete_watchlist(item_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    service.delete_item(db, settings.default_tenant_id, item_id)
    return {"status": "deleted", "id": item_id}
