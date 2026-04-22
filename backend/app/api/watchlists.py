from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.schemas.watchlist import WatchlistCreate, WatchlistRead
from app.watchlist.service import WatchlistService

router = APIRouter(prefix="/watchlists")
service = WatchlistService()


@router.get("", response_model=list[WatchlistRead])
def list_watchlists(db: Session = Depends(get_db)) -> list[WatchlistRead]:
    items = service.list_items(db, settings.default_tenant_id)
    return [WatchlistRead.model_validate(item) for item in items]


@router.post("", response_model=WatchlistRead)
def create_watchlist(payload: WatchlistCreate, db: Session = Depends(get_db)) -> WatchlistRead:
    item = service.create_item(db, settings.default_tenant_id, payload.symbol)
    return WatchlistRead.model_validate(item)


@router.delete("/{item_id}")
def delete_watchlist(item_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    service.delete_item(db, settings.default_tenant_id, item_id)
    return {"status": "deleted", "id": item_id}
