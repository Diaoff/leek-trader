from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessException, NotFoundException
from app.models.watchlist import WatchlistItem


class WatchlistService:
    def list_items(self, db: Session, tenant_id: str) -> list[WatchlistItem]:
        return db.scalars(
            select(WatchlistItem)
            .where(WatchlistItem.tenant_id == tenant_id)
            .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
        ).all()

    def create_item(self, db: Session, tenant_id: str, symbol: str) -> WatchlistItem:
        normalized_symbol = self._normalize_symbol(symbol)

        existing = db.scalar(
            select(WatchlistItem).where(
                WatchlistItem.tenant_id == tenant_id,
                WatchlistItem.symbol == normalized_symbol,
            )
        )
        if existing is not None:
            raise BusinessException("symbol already exists in watchlist")

        max_sort_order = db.scalar(
            select(func.coalesce(func.max(WatchlistItem.sort_order), -1)).where(WatchlistItem.tenant_id == tenant_id)
        )
        item = WatchlistItem(
            tenant_id=tenant_id,
            symbol=normalized_symbol,
            sort_order=int(max_sort_order) + 1,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def delete_item(self, db: Session, tenant_id: str, item_id: int) -> None:
        item = db.scalar(
            select(WatchlistItem).where(
                WatchlistItem.id == item_id,
                WatchlistItem.tenant_id == tenant_id,
            )
        )
        if item is None:
            raise NotFoundException("watchlist item not found")

        db.delete(item)
        db.commit()

    def _normalize_symbol(self, symbol: str) -> str:
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            raise BusinessException("symbol is required")
        return normalized_symbol
