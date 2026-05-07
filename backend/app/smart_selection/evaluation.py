from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market.history_storage import MarketDailyBarStorage
from app.models.smart_selection_item import SmartSelectionItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus


@dataclass(slots=True)
class ForwardPerformance:
    status: str
    entry_date: str | None = None
    entry_price: float | None = None
    exit_date: str | None = None
    exit_price: float | None = None
    forward_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    target_hit: bool = False
    stop_hit: bool = False
    holding_days: int = 0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "entry_date": self.entry_date,
            "entry_price": self.entry_price,
            "exit_date": self.exit_date,
            "exit_price": self.exit_price,
            "forward_return_pct": self.forward_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "target_hit": self.target_hit,
            "stop_hit": self.stop_hit,
            "holding_days": self.holding_days,
            "reason": self.reason,
        }


class SmartSelectionScoringEvaluator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.storage = MarketDailyBarStorage(db)

    def evaluate_run(
        self,
        run_id: int,
        *,
        horizons: tuple[int, ...] = (1, 3, 5, 10, 20),
        source: str = "baostock",
        adjustflag: str = "2",
        user_id: int | None = None,
    ) -> dict[str, Any]:
        run = self.db.get(SmartSelectionRun, run_id)
        if run is None or (run.user_id is not None and run.user_id != user_id):
            raise ValueError("smart selection run not found")
        items = self.db.scalars(
            select(SmartSelectionItem)
            .where(SmartSelectionItem.run_id == run_id)
            .order_by(SmartSelectionItem.score.desc(), SmartSelectionItem.id.asc())
        ).all()
        evaluations = []
        for item in items:
            horizon_results = {
                f"{horizon}d": self.evaluate_item(item, horizon_days=horizon, source=source, adjustflag=adjustflag).to_dict()
                for horizon in horizons
            }
            evaluations.append(
                {
                    "symbol": item.symbol,
                    "code": item.code,
                    "name": item.name,
                    "score": round(float(item.score), 2),
                    "enhanced_score": (item.raw_detail or {}).get("score_enhancement", {}).get("enhanced_score"),
                    "horizons": horizon_results,
                }
            )
        return {
            "run_id": run_id,
            "status": run.status.value if isinstance(run.status, SmartSelectionRunStatus) else str(run.status),
            "recommendation_count": len(items),
            "horizons": [f"{horizon}d" for horizon in horizons],
            "summary": self._summary(evaluations),
            "items": evaluations,
        }

    def evaluate_item(
        self,
        item: SmartSelectionItem,
        *,
        horizon_days: int = 5,
        source: str = "baostock",
        adjustflag: str = "2",
        user_id: int | None = None,
    ) -> ForwardPerformance:
        raw_detail = item.raw_detail or {}
        generated_date = self._generated_date(item)
        bars = self.storage.list_bars(
            symbol=item.symbol,
            source=source,
            adjustflag=adjustflag,
            start_date=generated_date,
            end_date=generated_date + timedelta(days=horizon_days + 10),
        ).bars
        future_bars = [bar for bar in bars if bar.trade_date >= generated_date]
        if len(future_bars) < 2:
            return ForwardPerformance(status="insufficient_data", reason="not enough future bars")
        window = future_bars[: horizon_days + 1]
        entry = window[0]
        exit_bar = window[-1]
        entry_price = float(item.price or entry.close_price)
        if entry_price <= 0:
            return ForwardPerformance(status="invalid", reason="entry price is not positive")
        lows = [float(bar.low_price) for bar in window[1:]] or [float(exit_bar.low_price)]
        highs = [float(bar.high_price) for bar in window[1:]] or [float(exit_bar.high_price)]
        stop_price = float(item.stop_loss_price or raw_detail.get("stop") or 0.0)
        target_price = float(item.target_price or raw_detail.get("target") or 0.0)
        return ForwardPerformance(
            status="ready",
            entry_date=entry.trade_date.isoformat(),
            entry_price=round(entry_price, 4),
            exit_date=exit_bar.trade_date.isoformat(),
            exit_price=round(float(exit_bar.close_price), 4),
            forward_return_pct=round((float(exit_bar.close_price) - entry_price) / entry_price * 100, 6),
            max_drawdown_pct=round(min(0.0, (min(lows) - entry_price) / entry_price * 100), 6),
            target_hit=bool(target_price and max(highs) >= target_price),
            stop_hit=bool(stop_price and min(lows) <= stop_price),
            holding_days=max(0, len(window) - 1),
        )

    @staticmethod
    def _generated_date(item: SmartSelectionItem) -> date:
        raw_detail = item.raw_detail or {}
        generated_at = raw_detail.get("generated_at") or raw_detail.get("trade_date")
        if isinstance(generated_at, str) and len(generated_at) >= 10:
            return date.fromisoformat(generated_at[:10])
        return item.created_at.date()

    @staticmethod
    def _summary(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
        by_horizon: dict[str, dict[str, Any]] = {}
        horizon_names = sorted({horizon for item in evaluations for horizon in item["horizons"]})
        for horizon in horizon_names:
            ready = [item["horizons"][horizon] for item in evaluations if item["horizons"][horizon]["status"] == "ready"]
            returns = [float(item["forward_return_pct"] or 0.0) for item in ready]
            by_horizon[horizon] = {
                "ready_count": len(ready),
                "average_return_pct": round(sum(returns) / len(returns), 6) if returns else None,
                "win_rate_pct": round(sum(1 for value in returns if value > 0) / len(returns) * 100, 6) if returns else None,
                "target_hit_count": sum(1 for item in ready if item["target_hit"]),
                "stop_hit_count": sum(1 for item in ready if item["stop_hit"]),
            }
        return by_horizon
