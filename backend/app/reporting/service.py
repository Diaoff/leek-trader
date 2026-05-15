import csv
import math
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import Account
from app.models.cash_flow import CashFlow
from app.models.equity_snapshot import EquitySnapshot
from app.models.event_log import EventLogType
from app.models.order import Order
from app.models.position import Position
from app.models.trade import Trade
from app.reporting.event_log_service import EventLogService

TWO_DP = Decimal("0.01")
TRADING_DAYS_PER_YEAR = 252
DEFAULT_ANNUAL_RISK_FREE_RATE = 0.025


class ReportingService:
    def __init__(self) -> None:
        self.event_log_service = EventLogService()

    def get_summary(self, db: Session, user_id: int | None = None) -> dict[str, float | int | None]:
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
                "annualized_return_pct": None,
                "annualized_volatility_pct": None,
                "sharpe_ratio": None,
                "calmar_ratio": None,
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
        snapshots = self._get_equity_snapshots(db, account.id)
        max_drawdown = self._calculate_max_drawdown_from_snapshots(snapshots)
        advanced_metrics = self._calculate_advanced_metrics(snapshots, max_drawdown)

        return {
            "trade_count": int(trade_count),
            "realized_pnl": float(realized_pnl),
            "win_rate": float(win_rate),
            "cumulative_return": float(cumulative_return),
            "profit_factor": float(profit_factor),
            "max_drawdown": float(max_drawdown),
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
            **advanced_metrics,
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

    def export_trades_csv(self, db: Session, user_id: int | None = None) -> str:
        account = self._default_account(db, user_id)
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["section", "id", "account_id", "symbol", "side_or_type", "status", "quantity", "price", "amount", "fee", "pnl", "timestamp", "reference", "note"])
        if account is None:
            return output.getvalue()

        for order in db.scalars(select(Order).where(Order.account_id == account.id).order_by(Order.created_at.asc(), Order.id.asc())).all():
            writer.writerow(["order", order.id, order.account_id, order.symbol, order.side.value, order.status.value, order.quantity, self._decimal_text(order.price), "", "", "", order.created_at.isoformat(), "", order.reject_reason or ""])
        for trade in db.scalars(select(Trade).where(Trade.account_id == account.id).order_by(Trade.executed_at.asc(), Trade.id.asc())).all():
            writer.writerow(["trade", trade.id, trade.account_id, trade.symbol, "fill", "filled", trade.quantity, self._decimal_text(trade.price), self._decimal_text(Decimal(trade.quantity) * trade.price), self._decimal_text(trade.fee), self._decimal_text(trade.realized_pnl), trade.executed_at.isoformat(), trade.order_id, ""])
        for flow in db.scalars(select(CashFlow).where(CashFlow.account_id == account.id).order_by(CashFlow.created_at.asc(), CashFlow.id.asc())).all():
            writer.writerow(["cash_flow", flow.id, flow.account_id, "", flow.flow_type.value, "", "", "", self._decimal_text(flow.amount), "", "", flow.created_at.isoformat(), flow.reference or "", flow.note or ""])
        for position in db.scalars(select(Position).where(Position.account_id == account.id).order_by(Position.symbol.asc(), Position.id.asc())).all():
            writer.writerow(["position", position.id, position.account_id, position.symbol, "snapshot", position.exit_guard_status, position.quantity, self._decimal_text(position.last_price), self._decimal_text(position.last_price * position.quantity), "", self._decimal_text(position.unrealized_pnl), position.updated_at.isoformat(), "", f"available={position.available_quantity}; average_cost={self._decimal_text(position.average_cost)}"])
        return output.getvalue()

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
        user_id: int | None = None,
        strategy_id: int | None = None,
        strategy_run_id: int | None = None,
        order_id: int | None = None,
        trade_id: int | None = None,
        correlation_id: str | None = None,
        symbol: str | None = None,
    ) -> EquitySnapshot:
        snapshot = EquitySnapshot(
            tenant_id=tenant_id,
            account_id=account_id,
            total_equity=total_equity.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            available_cash=available_cash.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            market_value=market_value.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            unrealized_pnl=unrealized_pnl.quantize(TWO_DP, rounding=ROUND_HALF_UP),
        )
        db.add(snapshot)
        db.flush()
        self.event_log_service.append(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            account_id=account_id,
            event_type=EventLogType.EQUITY_SNAPSHOT,
            symbol=symbol,
            strategy_id=strategy_id,
            strategy_run_id=strategy_run_id,
            order_id=order_id,
            trade_id=trade_id,
            equity_snapshot_id=snapshot.id,
            correlation_id=correlation_id,
            payload={
                "total_equity": float(snapshot.total_equity),
                "available_cash": float(snapshot.available_cash),
                "market_value": float(snapshot.market_value),
                "unrealized_pnl": float(snapshot.unrealized_pnl),
                "degraded_reason": "legacy_snapshot_without_order_context" if order_id is None and strategy_run_id is None else None,
            },
        )
        return snapshot

    def list_events(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        strategy_id: int | None = None,
        strategy_run_id: int | None = None,
        order_id: int | None = None,
        symbol: str | None = None,
        event_type: str | None = None,
        correlation_id: str | None = None,
    ) -> list[dict[str, object]]:
        events = self.event_log_service.query(
            db,
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
            strategy_id=strategy_id,
            strategy_run_id=strategy_run_id,
            order_id=order_id,
            symbol=symbol,
            event_type=event_type,
            correlation_id=correlation_id,
        )
        return [
            {
                "id": event.id,
                "tenant_id": event.tenant_id,
                "user_id": event.user_id,
                "account_id": event.account_id,
                "event_type": event.event_type.value,
                "symbol": event.symbol,
                "occurred_at": event.occurred_at,
                "strategy_id": event.strategy_id,
                "strategy_run_id": event.strategy_run_id,
                "order_id": event.order_id,
                "order_event_id": event.order_event_id,
                "trade_id": event.trade_id,
                "position_id": event.position_id,
                "equity_snapshot_id": event.equity_snapshot_id,
                "correlation_id": event.correlation_id,
                "risk_rule_version": event.risk_rule_version,
                "payload": event.payload,
            }
            for event in events
        ]

    def _calculate_max_drawdown(self, db: Session, account_id: int) -> float:
        return self._calculate_max_drawdown_from_snapshots(self._get_equity_snapshots(db, account_id))

    def _get_equity_snapshots(self, db: Session, account_id: int) -> list[EquitySnapshot]:
        return list(db.scalars(
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account_id)
            .order_by(EquitySnapshot.recorded_at.asc(), EquitySnapshot.id.asc())
        ).all())

    @staticmethod
    def _calculate_max_drawdown_from_snapshots(snapshots: list[EquitySnapshot]) -> float:
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

    @staticmethod
    def _calculate_advanced_metrics(snapshots: list[EquitySnapshot], max_drawdown: float) -> dict[str, float | None]:
        metrics: dict[str, float | None] = {
            "annualized_return_pct": None,
            "annualized_volatility_pct": None,
            "sharpe_ratio": None,
            "calmar_ratio": None,
        }
        usable_points = [(snapshot.recorded_at, float(snapshot.total_equity)) for snapshot in snapshots]
        if len(usable_points) < 2:
            return metrics

        start_at, start_equity = usable_points[0]
        end_at, end_equity = usable_points[-1]
        if start_equity <= 0 or end_equity <= 0:
            return metrics

        elapsed_days = max((ReportingService._as_naive_datetime(end_at) - ReportingService._as_naive_datetime(start_at)).total_seconds() / 86400, 1)
        annualized_return = math.pow(end_equity / start_equity, 365 / elapsed_days) - 1

        period_returns: list[float] = []
        previous_equity = start_equity
        for _, equity in usable_points[1:]:
            if previous_equity <= 0:
                return metrics
            period_returns.append((equity / previous_equity) - 1)
            previous_equity = equity

        annualized_volatility = None
        if len(period_returns) >= 2:
            mean_return = sum(period_returns) / len(period_returns)
            variance = sum((value - mean_return) ** 2 for value in period_returns) / (len(period_returns) - 1)
            annualized_volatility = math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)

        metrics["annualized_return_pct"] = annualized_return * 100
        metrics["annualized_volatility_pct"] = annualized_volatility * 100 if annualized_volatility is not None else None
        if annualized_volatility is not None and annualized_volatility > 0:
            metrics["sharpe_ratio"] = (annualized_return - DEFAULT_ANNUAL_RISK_FREE_RATE) / annualized_volatility
        if max_drawdown > 0:
            metrics["calmar_ratio"] = annualized_return / max_drawdown
        return metrics

    @staticmethod
    def _as_naive_datetime(value: datetime) -> datetime:
        return value.replace(tzinfo=None) if value.tzinfo is not None else value

    @staticmethod
    def _decimal_text(value: Decimal | int | float) -> str:
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return format(value, "f")

    @staticmethod
    def _default_account(db: Session, user_id: int | None = None) -> Account | None:
        query = select(Account).where(
            Account.tenant_id == settings.default_tenant_id,
            Account.name == settings.default_account_name,
        )
        if user_id is None:
            query = query.order_by(Account.user_id.is_not(None).desc(), Account.id.asc())
        else:
            query = query.where(Account.user_id == user_id)
        return db.scalar(query)

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
