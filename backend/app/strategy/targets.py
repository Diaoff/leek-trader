from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.trading_calendar import market_trade_date, previous_trading_day
from app.models.position import Position
from app.models.smart_selection_item import SmartSelectionItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus
from app.models.strategy import Strategy, StrategyTargetType
from app.models.watchlist import WatchlistItem


class StrategyTargetResolver:
    def resolve_symbols(self, db: Session, strategy: Strategy) -> list[str]:
        target_type = strategy.target_type
        target_config = self.target_config(strategy)
        if target_type == StrategyTargetType.SINGLE_SYMBOL:
            symbol = str(target_config.get("symbol") or strategy.symbol or "").strip().lower()
            return [symbol] if symbol else []

        if target_type == StrategyTargetType.SPECIAL_ATTENTION:
            ordered = self.ordered_special_attention_symbols(db)
            seen = set(ordered)
            for symbol in self.latest_recommendation_symbols(db):
                if symbol in seen:
                    continue
                seen.add(symbol)
                ordered.append(symbol)
            for symbol in self.open_position_symbols(db):
                if symbol in seen:
                    continue
                seen.add(symbol)
                ordered.append(symbol)
            return ordered

        return []

    def ordered_special_attention_symbols(self, db: Session) -> list[str]:
        symbols = db.scalars(
            select(WatchlistItem.symbol)
            .where(
                WatchlistItem.tenant_id == settings.default_tenant_id,
                WatchlistItem.is_special_attention.is_(True),
            )
            .order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
        ).all()
        return self._dedupe_symbols(symbols)

    def open_position_symbols(self, db: Session) -> list[str]:
        symbols = db.scalars(
            select(Position.symbol)
            .where(
                Position.tenant_id == settings.default_tenant_id,
                Position.quantity > 0,
            )
            .order_by(Position.updated_at.asc(), Position.id.asc())
        ).all()
        return self._dedupe_symbols(symbols)

    def latest_recommendation_symbols(self, db: Session, *, now: datetime | None = None) -> list[str]:
        run = self.latest_recommendation_scope_run(db, now=now)
        if run is None:
            return []

        symbols = db.scalars(
            select(SmartSelectionItem.symbol)
            .where(SmartSelectionItem.run_id == run.id)
            .order_by(desc(SmartSelectionItem.score), SmartSelectionItem.id.asc())
        ).all()
        return self._dedupe_symbols(symbols)

    def latest_recommendation_scope_run(
        self,
        db: Session,
        *,
        now: datetime | None = None,
    ) -> SmartSelectionRun | None:
        reference_day = market_trade_date(now)
        previous_day = previous_trading_day(reference_day)
        latest_by_trade_day: dict[date, SmartSelectionRun] = {}

        runs = db.scalars(
            select(SmartSelectionRun)
            .where(
                SmartSelectionRun.tenant_id == settings.default_tenant_id,
                SmartSelectionRun.status == SmartSelectionRunStatus.SUCCEEDED,
            )
            .order_by(desc(SmartSelectionRun.started_at), desc(SmartSelectionRun.id))
        ).all()

        for run in runs:
            snapshot_at = recommendation_snapshot_datetime(run)
            if snapshot_at is None:
                continue
            snapshot_day = market_trade_date(snapshot_at)
            if snapshot_day not in latest_by_trade_day:
                latest_by_trade_day[snapshot_day] = run

        for target_day in (reference_day, previous_day):
            run = latest_by_trade_day.get(target_day)
            if run is not None:
                return run
        return None

    @staticmethod
    def primary_symbol(strategy: Strategy) -> str:
        target_config = strategy.target_config or {}
        if strategy.target_type == StrategyTargetType.SINGLE_SYMBOL:
            return str(target_config.get("symbol") or strategy.symbol or "")
        return ""

    def label(self, strategy: Strategy, resolved_symbols: list[str] | None = None) -> str:
        if strategy.target_type == StrategyTargetType.SINGLE_SYMBOL:
            return self.primary_symbol(strategy)
        if strategy.target_type == StrategyTargetType.SPECIAL_ATTENTION:
            symbols = resolved_symbols if resolved_symbols is not None else []
            if not symbols:
                return "重点关注空池"
            if len(symbols) == 1:
                return symbols[0]
            return f"{symbols[0]} 等 {len(symbols)} 只"
        return strategy.target_type.value

    @staticmethod
    def target_config(strategy: Strategy) -> dict[str, Any]:
        config = dict(strategy.target_config or {})
        if strategy.target_type == StrategyTargetType.SINGLE_SYMBOL:
            symbol = str(config.get("symbol") or strategy.symbol or "").strip().lower()
            config["symbol"] = symbol
        return config

    def normalize_payload(
        self,
        symbol: str | None,
        target_type: str | None,
        target_config: dict[str, Any] | None,
    ) -> tuple[StrategyTargetType, dict[str, Any], str]:
        parsed_target_type = self.parse_target_type(target_type or StrategyTargetType.SINGLE_SYMBOL.value)
        normalized_config = dict(target_config or {})
        normalized_symbol = str(symbol or normalized_config.get("symbol") or "").strip().lower()

        if parsed_target_type == StrategyTargetType.SINGLE_SYMBOL:
            if not normalized_symbol:
                raise HTTPException(status_code=422, detail="symbol is required for single_symbol strategies")
            normalized_config["symbol"] = normalized_symbol
            return parsed_target_type, normalized_config, normalized_symbol

        if parsed_target_type == StrategyTargetType.SPECIAL_ATTENTION:
            return parsed_target_type, normalized_config, ""

        raise HTTPException(status_code=422, detail=f"unsupported target_type: {parsed_target_type.value}")

    @staticmethod
    def parse_target_type(raw_target_type: str) -> StrategyTargetType:
        try:
            return StrategyTargetType(raw_target_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"unsupported target_type: {raw_target_type}") from exc

    @staticmethod
    def _dedupe_symbols(symbols: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for symbol in symbols:
            normalized = str(symbol or "").strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered


def recommendation_snapshot_datetime(run: SmartSelectionRun) -> datetime | None:
    return run.generated_at or run.finished_at or run.started_at
