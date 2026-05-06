import logging
from datetime import date

from sqlalchemy import select

from app.core.config import settings
from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.trading_calendar import is_trading_time
from app.market.baostock_sync_service import BaoStockHistorySyncService
from app.market.rl_experiment_service import RLExperimentService
from app.market.service import QuoteService
from app.market.symbols import normalize_a_share_symbol
from app.models.position import Position
from app.models.strategy import Strategy, StrategyStatus
from app.models.watchlist import WatchlistItem

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.market_tasks.refresh_market_quotes_task", bind=True)
def refresh_market_quotes_task(self, symbols: list[str] | None = None, scheduled: bool = False) -> dict[str, object]:
    if scheduled and not is_trading_time():
        logger.info(
            "Celery task skipped task=%s task_id=%s reason=outside_trading_hours",
            self.name,
            self.request.id,
        )
        return _outside_trading_hours_result("refresh_market_quotes")

    if symbols is None:
        with SessionLocal() as db:
            target_symbols = _resolve_refresh_symbols(db)
    else:
        target_symbols = _normalize_symbols(symbols)
    logger.info(
        "Celery task started task=%s task_id=%s symbols=%s",
        self.name,
        self.request.id,
        target_symbols,
    )
    if not target_symbols:
        result = {
            "status": "skipped",
            "task": "refresh_market_quotes",
            "symbols": [],
            "count": 0,
        }
        logger.info(
            "Celery task skipped task=%s task_id=%s reason=no_symbols",
            self.name,
            self.request.id,
        )
        return result
    quotes = QuoteService().refresh_quotes(target_symbols)
    result = {
        "status": "refreshed",
        "task": "refresh_market_quotes",
        "symbols": target_symbols,
        "count": len(quotes),
    }
    logger.info(
        "Celery task succeeded task=%s task_id=%s count=%s",
        self.name,
        self.request.id,
        result["count"],
    )
    return result


def refresh_market_quotes() -> dict[str, object]:
    return refresh_market_quotes_task()


@celery_app.task(name="app.tasks.market_tasks.sync_baostock_history_task", bind=True)
def sync_baostock_history_task(
    self,
    symbols: list[str],
    start_date: str,
    end_date: str,
    adjustflag: str = "2",
    incremental: bool = False,
) -> dict[str, object]:
    target_symbols = _normalize_a_share_symbols(symbols or [])
    if not target_symbols:
        raise ValueError("symbols must be a non-empty explicit list")

    logger.info(
        "Celery task started task=%s task_id=%s symbols=%s start_date=%s end_date=%s adjustflag=%s incremental=%s",
        self.name,
        self.request.id,
        target_symbols,
        start_date,
        end_date,
        adjustflag,
        incremental,
    )

    def progress(step: int, total: int, label: str, details: list[str]) -> None:
        pct = round((step / total) * 100, 2) if total else 0.0
        self.update_state(
            state="PROGRESS",
            meta={
                "progress_step": step,
                "progress_total": total,
                "progress_pct": pct,
                "progress_label": label,
                "progress_details": details,
            },
        )
        logger.info(
            "BaoStock history sync progress task=%s task_id=%s step=%s total=%s label=%s details=%s",
            self.name,
            self.request.id,
            step,
            total,
            label,
            details,
        )

    with SessionLocal() as db:
        result = BaoStockHistorySyncService(db).sync_history(
            symbols=target_symbols,
            start_date=date.fromisoformat(start_date),
            end_date=date.fromisoformat(end_date),
            adjustflag=adjustflag,
            incremental=incremental,
            progress_callback=progress,
        )
    payload = result.to_dict()
    logger.info(
        "Celery task completed task=%s task_id=%s status=%s success_count=%s failure_count=%s bars_upserted=%s",
        self.name,
        self.request.id,
        payload["status"],
        payload["success_count"],
        payload["failure_count"],
        payload["bars_upserted"],
    )
    return payload


@celery_app.task(name="app.tasks.market_tasks.run_rl_batch_evaluation_task", bind=True)
def run_rl_batch_evaluation_task(self, payload: dict[str, object]) -> dict[str, object]:
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        raise ValueError("symbols must be a non-empty explicit list")

    logger.info(
        "Celery task started task=%s task_id=%s symbols=%s",
        self.name,
        self.request.id,
        symbols,
    )
    with SessionLocal() as db:
        result = RLExperimentService(db).run_batch_evaluation(
            symbols=[str(symbol) for symbol in symbols],
            start_date=date.fromisoformat(str(payload["start_date"])) if payload.get("start_date") else None,
            end_date=date.fromisoformat(str(payload["end_date"])) if payload.get("end_date") else None,
            source=str(payload.get("source") or "baostock"),
            adjustflag=str(payload.get("adjustflag") or "2"),
            exclude_suspended=bool(payload.get("exclude_suspended", True)),
            policy=str(payload.get("policy") or "buy_and_hold"),
            initial_cash=float(payload.get("initial_cash") or 100000.0),
            commission_rate=float(payload.get("commission_rate") or 0.0003),
            slippage_rate=float(payload.get("slippage_rate") or 0.0002),
            reward_mode=str(payload.get("reward_mode") or "net_worth_change"),
            max_position_pct=float(payload.get("max_position_pct") if payload.get("max_position_pct") is not None else 1.0),
            ma_short_window=int(payload.get("ma_short_window") or 5),
            ma_long_window=int(payload.get("ma_long_window") or 20),
            action_sequence=payload.get("action_sequence") if isinstance(payload.get("action_sequence"), list) else None,
            action_encoding=str(payload.get("action_encoding") or "legacy_zero_based"),
        )
    logger.info(
        "Celery task completed task=%s task_id=%s success_count=%s failure_count=%s",
        self.name,
        self.request.id,
        result["success_count"],
        result["failure_count"],
    )
    return result


def _outside_trading_hours_result(task: str) -> dict[str, object]:
    return {
        "status": "skipped",
        "task": task,
        "reason": "outside_trading_hours",
        "scheduled": True,
    }


def _resolve_refresh_symbols(db) -> list[str]:
    candidates: list[str] = []
    candidates.extend(settings.market_refresh_symbol_list)
    candidates.extend(
        db.scalars(
            select(WatchlistItem.symbol)
            .where(WatchlistItem.tenant_id == settings.default_tenant_id)
            .order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
        ).all()
    )
    candidates.extend(
        db.scalars(
            select(Position.symbol)
            .where(Position.tenant_id == settings.default_tenant_id)
            .order_by(Position.updated_at.desc(), Position.id.desc())
        ).all()
    )
    candidates.extend(
        db.scalars(
            select(Strategy.symbol)
            .where(
                Strategy.tenant_id == settings.default_tenant_id,
                Strategy.status == StrategyStatus.ACTIVE,
            )
            .order_by(Strategy.updated_at.desc(), Strategy.id.desc())
        ).all()
    )
    return _normalize_symbols(candidates)


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol or normalized_symbol in seen:
            continue
        seen.add(normalized_symbol)
        normalized.append(normalized_symbol)
    return normalized


def _normalize_a_share_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol or normalized_symbol in seen:
            continue
        seen.add(normalized_symbol)
        normalized.append(normalized_symbol)
    return normalized
