from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
import time

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot
from app.models.account import Account, AccountStatus
from app.models.cash_flow import CashFlow
from app.models.equity_snapshot import EquitySnapshot
from app.models.market_daily_bar import MarketDailyBar
from app.models.order import Order
from app.models.position import Position
from app.models.trade import Trade
from app.backtest.service import BacktestService
from app.market.quality_service import MarketDataQualityService
from app.reporting.service import ReportingService
from app.risk.service import RiskService

RESET_CONFIRMATION = "RESET"


class DevResetService:
    def reset_trading_state(
        self,
        db: Session,
        *,
        confirmation: str,
        tenant_id: str | None = None,
        initial_cash: Decimal | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        if confirmation != RESET_CONFIRMATION:
            raise ValueError("confirmation must be RESET")

        resolved_tenant_id = tenant_id or settings.default_tenant_id
        cash = initial_cash or Decimal("1000000.00")
        account = self._get_or_create_account(db, resolved_tenant_id, cash, user_id)
        counts = {
            "trades": self._count(db, Trade, account.id),
            "orders": self._count(db, Order, account.id),
            "positions": self._count(db, Position, account.id),
            "cash_flows": self._count(db, CashFlow, account.id),
            "equity_snapshots": self._count(db, EquitySnapshot, account.id),
        }

        db.execute(delete(Trade).where(Trade.account_id == account.id))
        db.execute(delete(Order).where(Order.account_id == account.id))
        db.execute(delete(Position).where(Position.account_id == account.id))
        db.execute(delete(CashFlow).where(CashFlow.account_id == account.id))
        db.execute(delete(EquitySnapshot).where(EquitySnapshot.account_id == account.id))

        account.initial_cash = cash
        account.available_cash = cash
        account.frozen_cash = Decimal("0.00")
        account.total_equity = cash
        account.status = AccountStatus.ACTIVE
        db.add(account)
        db.commit()
        db.refresh(account)

        return {
            "account_id": account.id,
            "tenant_id": account.tenant_id,
            "account_name": account.name,
            "initial_cash": str(account.initial_cash),
            "available_cash": str(account.available_cash),
            "total_equity": str(account.total_equity),
            "deleted_counts": counts,
        }

    def _get_or_create_account(self, db: Session, tenant_id: str, initial_cash: Decimal, user_id: int | None = None) -> Account:
        account = db.scalar(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.user_id == user_id,
                Account.name == settings.default_account_name,
            )
        )
        if account is not None:
            return account
        account = Account(
            tenant_id=tenant_id,
            user_id=user_id,
            name=settings.default_account_name,
            currency="CNY",
            initial_cash=initial_cash,
            available_cash=initial_cash,
            frozen_cash=Decimal("0.00"),
            total_equity=initial_cash,
            status=AccountStatus.ACTIVE,
        )
        db.add(account)
        db.flush()
        return account

    @staticmethod
    def _count(db: Session, model: type, account_id: int) -> int:
        return int(db.scalar(select(func.count(model.id)).where(model.account_id == account_id)) or 0)

    def benchmark_system(self, db: Session, *, user_id: int | None = None) -> dict[str, Any]:
        sample_symbol = "sh998888"
        sample_source = "benchmark"
        start_date = datetime(2026, 4, 1, tzinfo=timezone.utc).date()
        storage = MarketDailyBarStorage(db)
        existing_bars = storage.list_bars(
            symbol=sample_symbol,
            source=sample_source,
            adjustflag="2",
            start_date=start_date,
            end_date=start_date + timedelta(days=39),
        ).bars
        bars = [
            DailyBarSnapshot(
                symbol=sample_symbol,
                trade_date=start_date + timedelta(days=index),
                open_price=10.0 + index * 0.1,
                close_price=10.2 + index * 0.1,
                high_price=10.4 + index * 0.1,
                low_price=9.8 + index * 0.1,
                volume=1_000_000.0 + index * 1_000.0,
                turnover=10_000_000.0 + index * 10_000.0,
                trade_status=1,
                pe_ttm=12.0,
            )
            for index in range(40)
        ]
        storage.upsert_bars(bars, source=sample_source, adjustflag="2")
        benchmark_trade_dates = [bar.trade_date for bar in bars]

        samples: dict[str, dict[str, float | int | str]] = {}
        try:
            market_quality_service = MarketDataQualityService(db)
            backtest_service = BacktestService()
            reporting_service = ReportingService()
            risk_service = RiskService()

            market_start = time.perf_counter()
            quality_report = market_quality_service.build_daily_bar_quality_report(symbols=[sample_symbol], source=sample_source, adjustflag="2")
            market_elapsed = (time.perf_counter() - market_start) * 1000

            backtest_start = time.perf_counter()
            backtest_result = backtest_service.run_single_symbol_backtest(
                db,
                symbol=sample_symbol,
                strategy_type="moving_average",
                start_date=bars[0].trade_date,
                end_date=bars[-1].trade_date,
                source=sample_source,
                adjustflag="2",
                initial_cash=100000.0,
                commission_rate=0.0003,
                slippage_rate=0.0002,
                max_position_pct=1.0,
                parameters={"short_window": 3, "long_window": 5, "position_pct": 0.2},
                user_id=user_id,
            )
            backtest_elapsed = (time.perf_counter() - backtest_start) * 1000

            report_start = time.perf_counter()
            trades = [
                SimpleNamespace(executed_at=datetime(2026, 4, 1, tzinfo=timezone.utc), realized_pnl=Decimal("120.00")),
                SimpleNamespace(executed_at=datetime(2026, 4, 2, tzinfo=timezone.utc), realized_pnl=Decimal("-30.00")),
            ]
            snapshots = [
                SimpleNamespace(recorded_at=datetime(2026, 4, 1, tzinfo=timezone.utc), total_equity=Decimal("100000.00")),
                SimpleNamespace(recorded_at=datetime(2026, 4, 2, tzinfo=timezone.utc), total_equity=Decimal("100090.00")),
            ]
            period_stats = reporting_service._group_period_stats(trades, snapshots, "%Y-%m")
            report_elapsed = (time.perf_counter() - report_start) * 1000

            risk_start = time.perf_counter()
            risk_result = risk_service.validate_order(
                quantity=100,
                price=100.0,
                available_cash=100000.0,
                total_equity=100000.0,
                current_position_value=0.0,
                total_position_value=0.0,
                is_halted=False,
                is_limit_up=False,
                is_limit_down=False,
                is_trading_time=True,
                is_sell=False,
                daily_trade_count=0,
                daily_loss_rate=0.0,
            )
            risk_elapsed = (time.perf_counter() - risk_start) * 1000

            samples = {
                "market_processing": {
                    "kind": "daily_bar_quality_report",
                    "rows": quality_report.total_rows,
                    "elapsed_ms": round(market_elapsed, 4),
                },
                "backtest": {
                    "kind": "single_symbol_backtest",
                    "bars": int(backtest_result.get("bars", 0)),
                    "elapsed_ms": round(backtest_elapsed, 4),
                },
                "reporting": {
                    "kind": "period_stats_grouping",
                    "periods": len(period_stats),
                    "elapsed_ms": round(report_elapsed, 4),
                },
                "risk_validation": {
                    "kind": "order_risk_validation",
                    "checks": len(risk_result.checks),
                    "elapsed_ms": round(risk_elapsed, 4),
                },
            }
            total_elapsed = round(market_elapsed + backtest_elapsed + report_elapsed + risk_elapsed, 4)
            summary = {
                "status": "ready",
                "sample_count": len(samples),
                "total_objects": len(samples),
                "total_elapsed_ms": total_elapsed,
                "median_elapsed_ms": round(sorted(sample["elapsed_ms"] for sample in samples.values())[len(samples) // 2], 4),
                "observed_account": bool(
                    db.scalar(
                        select(Account.id).where(
                            Account.tenant_id == settings.default_tenant_id,
                            Account.name == settings.default_account_name,
                            Account.user_id == user_id,
                        )
                    )
                ),
            }
            return {
                "status": "ready",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "samples": samples,
                "summary": summary,
            }
        finally:
            db.execute(
                delete(MarketDailyBar).where(
                    MarketDailyBar.symbol == sample_symbol,
                    MarketDailyBar.source == sample_source,
                    MarketDailyBar.adjustflag == "2",
                    MarketDailyBar.trade_date.in_(benchmark_trade_dates),
                )
            )
            if existing_bars:
                storage.upsert_bars(existing_bars, source=sample_source, adjustflag="2")
            db.commit()
