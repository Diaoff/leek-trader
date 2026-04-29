from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import Account, AccountStatus
from app.models.cash_flow import CashFlow
from app.models.equity_snapshot import EquitySnapshot
from app.models.order import Order
from app.models.position import Position
from app.models.trade import Trade

RESET_CONFIRMATION = "RESET"


class DevResetService:
    def reset_trading_state(
        self,
        db: Session,
        *,
        confirmation: str,
        tenant_id: str | None = None,
        initial_cash: Decimal | None = None,
    ) -> dict[str, Any]:
        if confirmation != RESET_CONFIRMATION:
            raise ValueError("confirmation must be RESET")

        resolved_tenant_id = tenant_id or settings.default_tenant_id
        cash = initial_cash or Decimal(str(settings.default_initial_cash))
        account = self._get_or_create_account(db, resolved_tenant_id, cash)
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

    def _get_or_create_account(self, db: Session, tenant_id: str, initial_cash: Decimal) -> Account:
        account = db.scalar(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.name == settings.default_account_name,
            )
        )
        if account is not None:
            return account
        account = Account(
            tenant_id=tenant_id,
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
