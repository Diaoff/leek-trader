from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.watchlist import WatchlistCreate, WatchlistRead, WatchlistReorderPayload, WatchlistUpdate
from app.watchlist.service import WatchlistService

router = APIRouter(prefix="/watchlists")
service = WatchlistService()


@router.get("", response_model=list[WatchlistRead])
def list_watchlists(
    group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[WatchlistRead]:
    return service.list_items(db, settings.default_tenant_id, group_id, current_user.id)


@router.post("", response_model=WatchlistRead)
def create_watchlist(
    payload: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> WatchlistRead:
    return service.create_item(db, settings.default_tenant_id, payload, current_user.id)


@router.patch("/{item_id}", response_model=WatchlistRead)
def update_watchlist(
    item_id: int,
    payload: WatchlistUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> WatchlistRead:
    return service.update_item(db, settings.default_tenant_id, item_id, payload, current_user.id)


@router.post("/reorder")
def reorder_watchlists(
    payload: WatchlistReorderPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, str]:
    service.reorder_items(
        db,
        settings.default_tenant_id,
        payload.group_id,
        payload.pinned_ids,
        payload.regular_ids,
        current_user.id,
    )
    return {"status": "ok"}


@router.delete("/{item_id}")
def delete_watchlist(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, object]:
    service.delete_item(db, settings.default_tenant_id, item_id, current_user.id)
    return {"status": "deleted", "id": item_id}
