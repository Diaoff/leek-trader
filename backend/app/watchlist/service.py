from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessException, NotFoundException
from app.market.security_catalog import find_security_by_symbol
from app.models.watchlist import WatchlistItem
from app.models.watchlist_group import WatchlistGroup
from app.schemas.watchlist import (
    WatchlistCreate,
    WatchlistGroupRead,
    WatchlistRead,
    WatchlistUpdate,
)


DEFAULT_GROUP_NAMES = ["价投", "观察股", "T0", "清仓", "现"]
DEFAULT_CREATE_GROUP = "价投"
DELETE_FALLBACK_GROUP = "观察股"


class WatchlistService:
    def ensure_default_groups(self, db: Session, tenant_id: str, user_id: int | None = None) -> list[WatchlistGroup]:
        groups = self._list_groups(db, tenant_id, user_id)

        existing_names = {group.name for group in groups}
        created = False
        for index, name in enumerate(DEFAULT_GROUP_NAMES):
            if name in existing_names:
                continue
            db.add(
                WatchlistGroup(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    name=name,
                    is_system=True,
                    sort_order=index,
                )
            )
            created = True

        if created:
            db.flush()
            groups = self._list_groups(db, tenant_id, user_id)

        default_group = next((group for group in groups if group.name == DEFAULT_CREATE_GROUP), groups[0] if groups else None)
        if default_group is not None:
            unassigned_items = db.scalars(
                select(WatchlistItem).where(
                    WatchlistItem.tenant_id == tenant_id,
                    WatchlistItem.user_id == user_id,
                    WatchlistItem.group_id.is_(None),
                )
            ).all()
            for item in unassigned_items:
                item.group_id = default_group.id

        return groups

    def list_groups(self, db: Session, tenant_id: str, user_id: int | None = None) -> list[WatchlistGroupRead]:
        groups = self._list_groups(db, tenant_id, user_id)
        counts = dict(
            db.execute(
                select(WatchlistItem.group_id, func.count(WatchlistItem.id))
                .where(WatchlistItem.tenant_id == tenant_id, WatchlistItem.user_id == user_id)
                .group_by(WatchlistItem.group_id)
            ).all()
        )
        return [
            WatchlistGroupRead(
                id=group.id,
                tenant_id=group.tenant_id,
                name=group.name,
                is_system=group.is_system,
                sort_order=group.sort_order,
                item_count=counts.get(group.id, 0),
                created_at=group.created_at,
            )
            for group in groups
        ]

    def create_group(self, db: Session, tenant_id: str, name: str, user_id: int | None = None) -> WatchlistGroupRead:
        normalized_name = self._normalize_group_name(name)

        existing = db.scalar(
            select(WatchlistGroup).where(
                WatchlistGroup.tenant_id == tenant_id,
                WatchlistGroup.user_id == user_id,
                WatchlistGroup.name == normalized_name,
            )
        )
        if existing is not None:
            raise BusinessException("watchlist group already exists")

        max_sort_order = db.scalar(
            select(func.coalesce(func.max(WatchlistGroup.sort_order), -1)).where(
                WatchlistGroup.tenant_id == tenant_id,
                WatchlistGroup.user_id == user_id,
            )
        )
        group = WatchlistGroup(
            tenant_id=tenant_id,
            user_id=user_id,
            name=normalized_name,
            is_system=False,
            sort_order=int(max_sort_order) + 1,
        )
        db.add(group)
        db.commit()
        db.refresh(group)
        return WatchlistGroupRead(
            id=group.id,
            tenant_id=group.tenant_id,
            name=group.name,
            is_system=group.is_system,
            sort_order=group.sort_order,
            item_count=0,
            created_at=group.created_at,
        )

    def update_group(self, db: Session, tenant_id: str, group_id: int, name: str | None, user_id: int | None = None) -> WatchlistGroupRead:
        group = self._get_group(db, tenant_id, group_id, user_id)
        if name is not None:
            normalized_name = self._normalize_group_name(name)
            existing = db.scalar(
                select(WatchlistGroup).where(
                    WatchlistGroup.tenant_id == tenant_id,
                    WatchlistGroup.user_id == user_id,
                    WatchlistGroup.name == normalized_name,
                    WatchlistGroup.id != group.id,
                )
            )
            if existing is not None:
                raise BusinessException("watchlist group already exists")
            group.name = normalized_name

        db.commit()
        db.refresh(group)
        return WatchlistGroupRead(
            id=group.id,
            tenant_id=group.tenant_id,
            name=group.name,
            is_system=group.is_system,
            sort_order=group.sort_order,
            item_count=self._count_group_items(db, tenant_id, group.id, user_id),
            created_at=group.created_at,
        )

    def reorder_groups(self, db: Session, tenant_id: str, group_ids: Sequence[int], user_id: int | None = None) -> None:
        groups = self._list_groups(db, tenant_id, user_id)
        existing_ids = {group.id for group in groups}
        if set(group_ids) != existing_ids:
            raise BusinessException("invalid watchlist group ordering")

        group_map = {group.id: group for group in groups}
        for index, group_id in enumerate(group_ids):
            group_map[group_id].sort_order = index

        db.commit()

    def delete_group(self, db: Session, tenant_id: str, group_id: int, user_id: int | None = None) -> None:
        groups = self._list_groups(db, tenant_id, user_id)
        group = next((entry for entry in groups if entry.id == group_id), None)
        if group is None:
            raise NotFoundException("watchlist group not found")
        remaining_groups = [entry for entry in groups if entry.id != group.id]
        fallback_group = next(
            (entry for entry in remaining_groups if entry.name == DELETE_FALLBACK_GROUP),
            remaining_groups[0] if remaining_groups else None,
        )
        items = db.scalars(
            select(WatchlistItem).where(
                WatchlistItem.tenant_id == tenant_id,
                WatchlistItem.user_id == user_id,
                WatchlistItem.group_id == group.id,
            )
        ).all()
        if items:
            next_order = self._next_sort_order(db, tenant_id, fallback_group.id, pinned=False, user_id=user_id) if fallback_group else 0
            for index, item in enumerate(items):
                item.group_id = fallback_group.id if fallback_group else None
                item.is_pinned = False
                item.sort_order = next_order + index

        db.delete(group)
        db.commit()

    def list_items(self, db: Session, tenant_id: str, group_id: int | None = None, user_id: int | None = None) -> list[WatchlistRead]:
        statement = (
            select(WatchlistItem)
            .where(WatchlistItem.tenant_id == tenant_id, WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
        )
        if group_id is not None:
            self._get_group(db, tenant_id, group_id, user_id)
            statement = statement.where(WatchlistItem.group_id == group_id)

        items = db.scalars(statement).all()
        return [self._serialize_item(item) for item in items]

    def create_item(self, db: Session, tenant_id: str, payload: WatchlistCreate, user_id: int | None = None) -> WatchlistRead:
        groups = self._list_groups(db, tenant_id, user_id)
        normalized_symbol = self._normalize_symbol(payload.symbol)

        existing = db.scalar(
            select(WatchlistItem).where(
                WatchlistItem.tenant_id == tenant_id,
                WatchlistItem.user_id == user_id,
                WatchlistItem.symbol == normalized_symbol,
            )
        )
        if existing is not None:
            raise BusinessException("symbol already exists in watchlist")

        group = self._resolve_group(groups, payload.group_id, DEFAULT_CREATE_GROUP)
        item = WatchlistItem(
            tenant_id=tenant_id,
            user_id=user_id,
            symbol=normalized_symbol,
            group_id=group.id,
            sort_order=self._next_sort_order(db, tenant_id, group.id, pinned=False, user_id=user_id),
            note=self._normalize_note(payload.note),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return self._serialize_item(item)

    def update_item(self, db: Session, tenant_id: str, item_id: int, payload: WatchlistUpdate, user_id: int | None = None) -> WatchlistRead:
        groups = self._list_groups(db, tenant_id, user_id)
        item = self._get_item(db, tenant_id, item_id, user_id)
        changed_fields = payload.model_fields_set

        target_group_id = item.group_id
        target_is_pinned = item.is_pinned

        if "group_id" in changed_fields and payload.group_id is not None:
            target_group = self._resolve_group(groups, payload.group_id, DEFAULT_CREATE_GROUP)
            target_group_id = target_group.id

        if "is_pinned" in changed_fields and payload.is_pinned is not None:
            target_is_pinned = payload.is_pinned

        if target_group_id != item.group_id or target_is_pinned != item.is_pinned:
            item.group_id = target_group_id
            item.is_pinned = target_is_pinned
            item.sort_order = self._next_sort_order(db, tenant_id, target_group_id, pinned=target_is_pinned, user_id=user_id)

        if "note" in changed_fields:
            item.note = self._normalize_note(payload.note)
        if "is_special_attention" in changed_fields and payload.is_special_attention is not None:
            item.is_special_attention = payload.is_special_attention

        db.commit()
        db.refresh(item)
        return self._serialize_item(item)

    def reorder_items(
        self,
        db: Session,
        tenant_id: str,
        group_id: int,
        pinned_ids: Sequence[int],
        regular_ids: Sequence[int],
        user_id: int | None = None,
    ) -> None:
        self.ensure_default_groups(db, tenant_id, user_id)
        group = self._get_group(db, tenant_id, group_id, user_id)
        items = db.scalars(
            select(WatchlistItem).where(
                WatchlistItem.tenant_id == tenant_id,
                WatchlistItem.user_id == user_id,
                WatchlistItem.group_id == group.id,
            )
        ).all()
        item_map = {item.id: item for item in items}
        expected_ids = set(item_map)
        received_ids = set(pinned_ids) | set(regular_ids)
        if expected_ids != received_ids or set(pinned_ids) & set(regular_ids):
            raise BusinessException("invalid watchlist ordering")

        for index, item_id in enumerate(pinned_ids):
            item_map[item_id].is_pinned = True
            item_map[item_id].sort_order = index

        for index, item_id in enumerate(regular_ids):
            item_map[item_id].is_pinned = False
            item_map[item_id].sort_order = index

        db.commit()

    def delete_item(self, db: Session, tenant_id: str, item_id: int, user_id: int | None = None) -> None:
        item = self._get_item(db, tenant_id, item_id, user_id)
        db.delete(item)
        db.commit()

    def _list_groups(self, db: Session, tenant_id: str, user_id: int | None = None) -> list[WatchlistGroup]:
        return db.scalars(
            select(WatchlistGroup)
            .where(WatchlistGroup.tenant_id == tenant_id, WatchlistGroup.user_id == user_id)
            .order_by(WatchlistGroup.sort_order.asc(), WatchlistGroup.id.asc())
        ).all()

    def _resolve_group(
        self,
        groups: Sequence[WatchlistGroup],
        group_id: int | None,
        fallback_name: str,
    ) -> WatchlistGroup:
        if group_id is not None:
            group = next((entry for entry in groups if entry.id == group_id), None)
            if group is None:
                raise NotFoundException("watchlist group not found")
            return group

        fallback = next((entry for entry in groups if entry.name == fallback_name), None)
        if fallback is None:
            raise NotFoundException("default watchlist group not found")
        return fallback

    def _count_group_items(self, db: Session, tenant_id: str, group_id: int, user_id: int | None = None) -> int:
        count = db.scalar(
            select(func.count(WatchlistItem.id)).where(
                WatchlistItem.tenant_id == tenant_id,
                WatchlistItem.user_id == user_id,
                WatchlistItem.group_id == group_id,
            )
        )
        return int(count or 0)

    def _next_sort_order(self, db: Session, tenant_id: str, group_id: int | None, pinned: bool, user_id: int | None = None) -> int:
        value = db.scalar(
            select(func.coalesce(func.max(WatchlistItem.sort_order), -1)).where(
                WatchlistItem.tenant_id == tenant_id,
                WatchlistItem.user_id == user_id,
                WatchlistItem.group_id == group_id,
                WatchlistItem.is_pinned == pinned,
            )
        )
        return int(value) + 1

    def _serialize_item(self, item: WatchlistItem) -> WatchlistRead:
        security = find_security_by_symbol(item.symbol)
        security_name = str(security["name"]) if security else item.symbol
        security_code = str(security["code"]) if security else item.symbol.removeprefix("sh").removeprefix("sz")
        market = str(security["market"]) if security else self._infer_market(item.symbol)
        tags = list(security.get("tags", [])) if security else self._infer_tags(item.symbol, security_name)
        if security is None:
            tags = self._infer_tags(item.symbol, security_name)

        return WatchlistRead(
            id=item.id,
            tenant_id=item.tenant_id,
            symbol=item.symbol,
            group_id=item.group_id,
            sort_order=item.sort_order,
            note=item.note,
            is_pinned=item.is_pinned,
            is_special_attention=item.is_special_attention,
            security_name=security_name,
            security_code=security_code,
            market=market,
            tags=tags,
            created_at=item.created_at,
        )

    def _get_item(self, db: Session, tenant_id: str, item_id: int, user_id: int | None = None) -> WatchlistItem:
        item = db.scalar(
            select(WatchlistItem).where(
                WatchlistItem.id == item_id,
                WatchlistItem.tenant_id == tenant_id,
                WatchlistItem.user_id == user_id,
            )
        )
        if item is None:
            raise NotFoundException("watchlist item not found")
        return item

    def _get_group(self, db: Session, tenant_id: str, group_id: int, user_id: int | None = None) -> WatchlistGroup:
        group = db.scalar(
            select(WatchlistGroup).where(
                WatchlistGroup.id == group_id,
                WatchlistGroup.tenant_id == tenant_id,
                WatchlistGroup.user_id == user_id,
            )
        )
        if group is None:
            raise NotFoundException("watchlist group not found")
        return group

    def _normalize_symbol(self, symbol: str) -> str:
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            raise BusinessException("symbol is required")
        return normalized_symbol

    def _normalize_group_name(self, name: str) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise BusinessException("group name is required")
        return normalized_name

    def _normalize_note(self, note: str | None) -> str | None:
        if note is None:
            return None
        normalized_note = note.strip()
        return normalized_note or None

    def _infer_market(self, symbol: str) -> str:
        if symbol.startswith("sh"):
            return "上海"
        if symbol.startswith("sz"):
            return "深圳"
        if symbol.startswith("bj"):
            return "北京"
        return "未知"

    def _infer_tags(self, symbol: str, name: str) -> list[str]:
        tags: list[str] = []
        if symbol.startswith("sh"):
            tags.append("沪市")
        elif symbol.startswith("sz"):
            tags.append("深市")
        elif symbol.startswith("bj"):
            tags.append("北交所")
        if "ST" in name.upper():
            tags.append("风险警示")
        return tags
