from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import Account
from app.models.equity_snapshot import EquitySnapshot
from app.models.trade import Trade

TWO_DP = Decimal("0.01")


class ReportingService:
    def get_summary(self, db: Session, user_id: int | None = None) -> dict[str, float | int]:
        query = select(Account).where(
            Account.tenant_id == settings.default_tenant_id,
            Account.name == settings.default_account_name,
        )
        if user_id is None:
            query = query.order_by(Account.user_id.is_not(None).desc(), Account.id.asc())
        else:
            query = query.where(Account.user_id == user_id)
        account = db.scalar(query)
        if account is None:
            return {
                "trade_count": 0,
                "realized_pnl": 0.0,
                "win_rate": 0.0,
                "cumulative_return": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
            }

        trade_count = db.scalar(select(func.count(Trade.id)).where(Trade.account_id == account.id)) or 0
        realized_pnl = db.scalar(select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(Trade.account_id == account.id)) or 0
        winning_trades = db.scalar(
            select(func.count(Trade.id)).where(Trade.account_id == account.id, Trade.realized_pnl > 0)
        ) or 0
        losing_trades = db.scalar(
            select(func.count(Trade.id)).where(Trade.account_id == account.id, Trade.realized_pnl < 0)
        ) or 0
        total_wins = db.scalar(
            select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(Trade.account_id == account.id, Trade.realized_pnl > 0)
        ) or 0
        total_losses = db.scalar(
            select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(Trade.account_id == account.id, Trade.realized_pnl < 0)
        ) or 0
        cumulative_return = 0.0 if float(account.initial_cash) == 0 else (float(account.total_equity) - float(account.initial_cash)) / float(account.initial_cash)
        win_rate = 0.0 if trade_count == 0 else winning_trades / trade_count
        profit_factor = 0.0 if float(total_losses) == 0 else float(total_wins) / abs(float(total_losses))
        avg_win = 0.0 if winning_trades == 0 else float(total_wins) / winning_trades
        avg_loss = 0.0 if losing_trades == 0 else float(total_losses) / losing_trades
        max_drawdown = self._calculate_max_drawdown(db, account.id)

        return {
            "trade_count": int(trade_count),
            "realized_pnl": float(realized_pnl),
            "win_rate": float(win_rate),
            "cumulative_return": float(cumulative_return),
            "profit_factor": float(profit_factor),
            "max_drawdown": float(max_drawdown),
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
        }

    def get_equity_curve(self, db: Session, user_id: int | None = None) -> list[dict[str, float | str]]:
        query = select(Account).where(
            Account.tenant_id == settings.default_tenant_id,
            Account.name == settings.default_account_name,
        )
        if user_id is None:
            query = query.order_by(Account.user_id.is_not(None).desc(), Account.id.asc())
        else:
            query = query.where(Account.user_id == user_id)
        account = db.scalar(query)
        if account is None:
            return []

        snapshots = db.scalars(
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account.id)
            .order_by(EquitySnapshot.recorded_at.asc(), EquitySnapshot.id.asc())
        ).all()
        return [
            {
                "label": snapshot.recorded_at.strftime("%m-%d %H:%M:%S"),
                "total_equity": float(snapshot.total_equity),
            }
            for snapshot in snapshots
        ]

    def get_monthly_stats(self, db: Session, user_id: int | None = None) -> list[dict[str, float | int | str]]:
        query = select(Account).where(
            Account.tenant_id == settings.default_tenant_id,
            Account.name == settings.default_account_name,
        )
        if user_id is None:
            query = query.order_by(Account.user_id.is_not(None).desc(), Account.id.asc())
        else:
            query = query.where(Account.user_id == user_id)
        account = db.scalar(query)
        if account is None:
            return []

        trades = db.scalars(select(Trade).where(Trade.account_id == account.id).order_by(Trade.executed_at.asc())).all()
        snapshots = db.scalars(
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account.id)
            .order_by(EquitySnapshot.recorded_at.asc(), EquitySnapshot.id.asc())
        ).all()
        return self._group_period_stats(trades, snapshots, "%Y-%m")

    def get_yearly_stats(self, db: Session, user_id: int | None = None) -> list[dict[str, float | int | str]]:
        query = select(Account).where(
            Account.tenant_id == settings.default_tenant_id,
            Account.name == settings.default_account_name,
        )
        if user_id is None:
            query = query.order_by(Account.user_id.is_not(None).desc(), Account.id.asc())
        else:
            query = query.where(Account.user_id == user_id)
        account = db.scalar(query)
        if account is None:
            return []

        trades = db.scalars(select(Trade).where(Trade.account_id == account.id).order_by(Trade.executed_at.asc())).all()
        snapshots = db.scalars(
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account.id)
            .order_by(EquitySnapshot.recorded_at.asc(), EquitySnapshot.id.asc())
        ).all()
        return self._group_period_stats(trades, snapshots, "%Y")

    def record_equity_snapshot(
        self,
        db: Session,
        *,
        account_id: int,
        tenant_id: str,
        total_equity: Decimal,
        available_cash: Decimal,
        market_value: Decimal,
        unrealized_pnl: Decimal,
    ) -> None:
        snapshot = EquitySnapshot(
            tenant_id=tenant_id,
            account_id=account_id,
            total_equity=total_equity.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            available_cash=available_cash.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            market_value=market_value.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            unrealized_pnl=unrealized_pnl.quantize(TWO_DP, rounding=ROUND_HALF_UP),
        )
        db.add(snapshot)

    def _calculate_max_drawdown(self, db: Session, account_id: int) -> float:
        snapshots = db.scalars(
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account_id)
            .order_by(EquitySnapshot.recorded_at.asc(), EquitySnapshot.id.asc())
        ).all()
        if not snapshots:
            return 0.0

        peak = float(snapshots[0].total_equity)
        max_drawdown = 0.0
        for snapshot in snapshots:
            equity = float(snapshot.total_equity)
            if equity > peak:
                peak = equity
            if peak > 0:
                drawdown = (peak - equity) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        return max_drawdown

    def _group_period_stats(self, trades: list[Trade], snapshots: list[EquitySnapshot], period_format: str) -> list[dict[str, float | int | str]]:
        periods: dict[str, dict[str, float | int | str]] = {}

        for trade in trades:
            period = trade.executed_at.strftime(period_format)
            item = periods.setdefault(period, {"period": period, "trade_count": 0, "realized_pnl": 0.0, "ending_equity": 0.0})
            item["trade_count"] = int(item["trade_count"]) + 1
            item["realized_pnl"] = float(item["realized_pnl"]) + float(trade.realized_pnl)

        for snapshot in snapshots:
            period = snapshot.recorded_at.strftime(period_format)
            item = periods.setdefault(period, {"period": period, "trade_count": 0, "realized_pnl": 0.0, "ending_equity": 0.0})
            item["ending_equity"] = float(snapshot.total_equity)

        return [periods[key] for key in sorted(periods.keys())]
