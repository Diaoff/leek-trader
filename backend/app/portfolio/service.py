from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.market.service import QuoteService
from app.models.account import Account
from app.models.position import Position
from app.reporting.service import ReportingService


TWO_DP = Decimal("0.01")
FOUR_DP = Decimal("0.0001")


class PortfolioService:
    def __init__(self, quote_service: QuoteService | None = None, reporting_service: ReportingService | None = None) -> None:
        self.quote_service = quote_service or QuoteService()
        self.reporting_service = reporting_service or ReportingService()

    def get_summary(self, db: Session, user_id: int | None = None) -> dict[str, float]:
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
                "total_equity": 0.0,
                "available_cash": 0.0,
                "frozen_cash": 0.0,
                "market_value": 0.0,
                "unrealized_pnl": 0.0,
            }

        self.refresh_positions_with_quotes(db, account.id)

        market_value = db.scalar(
            select(func.coalesce(func.sum(Position.quantity * Position.last_price), 0)).where(Position.account_id == account.id)
        ) or Decimal("0")
        unrealized_pnl = db.scalar(
            select(func.coalesce(func.sum(Position.unrealized_pnl), 0)).where(Position.account_id == account.id)
        ) or Decimal("0")
        account.total_equity = (account.available_cash + account.frozen_cash + market_value).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        self.reporting_service.record_equity_snapshot(
            db,
            account_id=account.id,
            tenant_id=account.tenant_id,
            total_equity=account.total_equity,
            available_cash=account.available_cash,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            user_id=account.user_id,
        )
        db.commit()
        db.refresh(account)

        return {
            "total_equity": float(account.total_equity),
            "available_cash": float(account.available_cash),
            "frozen_cash": float(account.frozen_cash),
            "market_value": float(market_value),
            "unrealized_pnl": float(unrealized_pnl),
        }

    def refresh_positions_with_quotes(self, db: Session, account_id: int) -> None:
        positions = db.scalars(
            select(Position).where(Position.account_id == account_id, Position.quantity > 0)
        ).all()
        if not positions:
            return

        snapshots = self.quote_service.list_quotes([position.symbol for position in positions])
        quote_map = {snapshot.symbol: snapshot for snapshot in snapshots}

        for position in positions:
            quote = quote_map.get(position.symbol)
            if quote is None:
                continue
            latest_price = Decimal(str(quote.price)).quantize(FOUR_DP, rounding=ROUND_HALF_UP)
            unrealized_pnl = ((latest_price - position.average_cost) * Decimal(position.quantity)).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            position.last_price = latest_price
            position.unrealized_pnl = unrealized_pnl

        db.flush()
