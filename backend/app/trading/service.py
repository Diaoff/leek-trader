from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.trading_calendar import market_trade_date
from app.market.service import QuoteService
from app.models.account import Account
from app.models.cash_flow import CashFlow, CashFlowType
from app.models.order import Order, OrderSide, OrderStatus, OrderType
from app.models.position import Position
from app.models.strategy import Strategy, StrategyStatus
from app.models.trade import Trade
from app.models.watchlist import WatchlistItem
from app.reporting.service import ReportingService
from app.risk.service import RiskService
from app.trading.matcher import TradeMatcher


FOUR_DP = Decimal("0.0001")
TWO_DP = Decimal("0.01")


class TradingService:
    def __init__(self, quote_service: QuoteService | None = None, reporting_service: ReportingService | None = None) -> None:
        self.risk_service = RiskService()
        self.matcher = TradeMatcher()
        self.quote_service = quote_service or QuoteService()
        self.reporting_service = reporting_service or ReportingService()

    def simulate_execution(self, db: Session, symbol: str, quantity: int = 100, price: float = 100.0) -> dict[str, object]:
        return self.place_order(
            db,
            symbol=symbol,
            side="buy",
            order_type="market",
            quantity=quantity,
            price=price,
            note_prefix="simulate buy",
        )

    def resolve_simulation_symbol(self, db: Session) -> str | None:
        symbol = db.scalar(
            select(WatchlistItem.symbol)
            .where(WatchlistItem.tenant_id == settings.default_tenant_id)
            .order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
            .limit(1)
        )
        if symbol:
            return symbol

        symbol = db.scalar(
            select(Position.symbol)
            .where(Position.tenant_id == settings.default_tenant_id)
            .order_by(Position.updated_at.desc(), Position.id.desc())
            .limit(1)
        )
        if symbol:
            return symbol

        return db.scalar(
            select(Strategy.symbol)
            .where(
                Strategy.tenant_id == settings.default_tenant_id,
                Strategy.status == StrategyStatus.ACTIVE,
            )
            .order_by(Strategy.updated_at.desc(), Strategy.id.desc())
            .limit(1)
        )

    def place_order(
        self,
        db: Session,
        *,
        symbol: str,
        side: Literal["buy", "sell"],
        order_type: Literal["market", "limit"],
        quantity: int,
        price: float,
        note_prefix: str | None = None,
    ) -> dict[str, object]:
        normalized_quantity = max((quantity // 100) * 100, 100)
        price_decimal = self._to_decimal(price, FOUR_DP)
        order_side = OrderSide(side)
        order_kind = OrderType(order_type)
        note_prefix = note_prefix or f"order {side}"

        account = self._get_default_account(db)
        if account is None:
            raise RuntimeError("default account not initialized")

        if order_kind == OrderType.LIMIT:
            order = Order(
                tenant_id=account.tenant_id,
                account_id=account.id,
                symbol=symbol,
                side=order_side,
                order_type=order_kind,
                status=OrderStatus.PENDING,
                quantity=normalized_quantity,
                price=price_decimal,
                filled_quantity=0,
                filled_price=Decimal("0.0000"),
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            return {
                "status": "accepted",
                "risk_checks": [],
                "execution": {"matched": False, "mode": "paper"},
                "order": {
                    "id": order.id,
                    "symbol": order.symbol,
                    "quantity": order.quantity,
                    "price": float(order.price),
                    "status": order.status.value,
                },
            }

        position = self._get_position(db, account.id, symbol)
        current_position_value = (position.quantity * position.last_price) if position is not None else Decimal("0")
        total_position_value = db.scalar(self._total_position_value_query(account.id)) or Decimal("0")
        quote = self._get_quote_snapshot(symbol)

        risk_result = self._validate_for_execution(
            db,
            account=account,
            position=position,
            side=side,
            quantity=normalized_quantity,
            price_decimal=price_decimal,
            current_position_value=current_position_value,
            total_position_value=total_position_value,
            quote=quote,
        )
        if not risk_result["passed"]:
            rejected_order = Order(
                tenant_id=account.tenant_id,
                account_id=account.id,
                symbol=symbol,
                side=order_side,
                order_type=order_kind,
                status=OrderStatus.REJECTED,
                quantity=normalized_quantity,
                price=price_decimal,
                filled_quantity=0,
                filled_price=Decimal("0.0000"),
                reject_reason=str(risk_result["rejection_reason"]),
            )
            db.add(rejected_order)
            db.commit()
            db.refresh(rejected_order)
            return {
                "status": "rejected",
                "risk_checks": risk_result["checks"],
                "rejection_reason": risk_result["rejection_reason"],
                "order": {
                    "id": rejected_order.id,
                    "symbol": rejected_order.symbol,
                    "quantity": rejected_order.quantity,
                    "price": float(rejected_order.price),
                    "status": rejected_order.status.value,
                    "reject_reason": rejected_order.reject_reason,
                },
            }

        order = Order(
            tenant_id=account.tenant_id,
            account_id=account.id,
            symbol=symbol,
            side=order_side,
            order_type=order_kind,
            status=OrderStatus.FILLED,
            quantity=normalized_quantity,
            price=price_decimal,
            filled_quantity=normalized_quantity,
            filled_price=price_decimal,
        )
        db.add(order)
        db.flush()

        payload = self._settle_filled_order(
            db,
            account=account,
            position=position,
            order=order,
            side=side,
            price_decimal=price_decimal,
            note_prefix=note_prefix,
        )
        db.commit()
        db.refresh(order)
        db.refresh(payload["trade"])
        db.refresh(payload["position"])
        db.refresh(account)

        return self._build_fill_response(order=order, account=account, risk_checks=risk_result["checks"], **payload)

    def cancel_order(self, db: Session, order_id: int) -> dict[str, object]:
        order = db.scalar(select(Order).where(Order.id == order_id))
        if order is None:
            return {"status": "not_found", "message": "order not found"}
        if order.status != OrderStatus.PENDING:
            return {"status": "rejected", "message": "only pending orders can be cancelled"}

        order.status = OrderStatus.CANCELLED
        db.commit()
        db.refresh(order)
        return {
            "status": "accepted",
            "order": {
                "id": order.id,
                "symbol": order.symbol,
                "status": order.status.value,
            },
        }

    def match_pending_orders(self, db: Session) -> dict[str, object]:
        pending_orders = db.scalars(
            select(Order)
            .where(Order.status == OrderStatus.PENDING, Order.order_type == OrderType.LIMIT)
            .order_by(Order.created_at.asc(), Order.id.asc())
        ).all()

        matched_orders: list[dict[str, object]] = []
        for order in pending_orders:
            quote = self._get_quote_snapshot(order.symbol)
            market_price = self._to_decimal(float(quote["price"]), FOUR_DP)
            should_fill = (
                order.side == OrderSide.BUY and market_price <= order.price
            ) or (
                order.side == OrderSide.SELL and market_price >= order.price
            )
            if not should_fill:
                continue

            account = db.scalar(select(Account).where(Account.id == order.account_id))
            if account is None:
                continue
            position = self._get_position(db, account.id, order.symbol)
            risk_result = self._validate_for_execution(
                db,
                account=account,
                position=position,
                side=order.side.value,
                quantity=order.quantity,
                price_decimal=order.price,
                current_position_value=(position.quantity * position.last_price) if position is not None else Decimal("0"),
                total_position_value=db.scalar(self._total_position_value_query(account.id)) or Decimal("0"),
                quote=quote,
            )
            if not risk_result["passed"]:
                continue

            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.filled_price = order.price
            payload = self._settle_filled_order(
                db,
                account=account,
                position=position,
                order=order,
                side=order.side.value,
                price_decimal=order.price,
                note_prefix=f"matched {order.side.value}",
            )
            matched_orders.append({
                "id": order.id,
                "symbol": order.symbol,
                "status": order.status.value,
                "filled_price": float(order.filled_price),
                "filled_quantity": order.filled_quantity,
            })

        db.commit()
        return {
            "status": "accepted",
            "matched_count": len(matched_orders),
            "matched_orders": matched_orders,
        }

    def _settle_filled_order(
        self,
        db: Session,
        *,
        account: Account,
        position: Position | None,
        order: Order,
        side: Literal["buy", "sell"],
        price_decimal: Decimal,
        note_prefix: str,
    ) -> dict[str, object]:
        normalized_quantity = order.quantity
        trade_value = self._to_decimal(normalized_quantity, FOUR_DP) * price_decimal
        execution = self.matcher.match(order.symbol, normalized_quantity, float(price_decimal))

        if side == "buy":
            cash_after = (account.available_cash - trade_value).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            realized_pnl = Decimal("0.00")
            trade_date = market_trade_date()

            if position is None:
                position = Position(
                    tenant_id=account.tenant_id,
                    account_id=account.id,
                    symbol=order.symbol,
                    market="CN",
                    quantity=0,
                    available_quantity=0,
                    frozen_quantity=0,
                    average_cost=Decimal("0.0000"),
                    last_price=Decimal("0.0000"),
                    unrealized_pnl=Decimal("0.00"),
                    realized_pnl=Decimal("0.00"),
                    strategy_add_count=0,
                    last_buy_date=trade_date,
                )
                db.add(position)
                db.flush()

            had_open_position = position.quantity > 0
            total_cost_before = position.average_cost * position.quantity
            new_total_quantity = position.quantity + normalized_quantity
            new_total_cost = total_cost_before + trade_value
            position.quantity = new_total_quantity
            position.available_quantity = new_total_quantity
            position.average_cost = (new_total_cost / Decimal(new_total_quantity)).quantize(FOUR_DP, rounding=ROUND_HALF_UP)
            position.last_price = price_decimal
            position.unrealized_pnl = Decimal("0.00")
            position.last_buy_date = trade_date
            position.strategy_add_count = position.strategy_add_count + 1 if had_open_position else 0
            cash_flow_amount = (-trade_value).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        else:
            assert position is not None
            realized_pnl = ((price_decimal - position.average_cost) * Decimal(normalized_quantity)).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            cash_after = (account.available_cash + trade_value).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            new_quantity = position.quantity - normalized_quantity
            position.quantity = new_quantity
            position.available_quantity = new_quantity
            position.realized_pnl = (position.realized_pnl + realized_pnl).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            position.last_price = price_decimal
            if new_quantity == 0:
                position.average_cost = Decimal("0.0000")
                position.last_price = Decimal("0.0000")
                position.unrealized_pnl = Decimal("0.00")
                position.strategy_add_count = 0
            cash_flow_amount = trade_value.quantize(TWO_DP, rounding=ROUND_HALF_UP)

        trade = Trade(
            tenant_id=account.tenant_id,
            account_id=account.id,
            order_id=order.id,
            symbol=order.symbol,
            quantity=normalized_quantity,
            price=price_decimal,
            fee=Decimal("0.00"),
            realized_pnl=realized_pnl,
        )
        db.add(trade)

        market_value = (Decimal(position.quantity) * position.last_price).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        account.available_cash = cash_after
        account.total_equity = (cash_after + market_value).quantize(TWO_DP, rounding=ROUND_HALF_UP)

        cash_flow = CashFlow(
            tenant_id=account.tenant_id,
            account_id=account.id,
            flow_type=CashFlowType.TRADE,
            amount=cash_flow_amount,
            balance_after=account.available_cash,
            reference=f"order:{order.id}",
            note=f"{note_prefix} {order.symbol}",
        )
        db.add(cash_flow)
        self.reporting_service.record_equity_snapshot(
            db,
            account_id=account.id,
            tenant_id=account.tenant_id,
            total_equity=account.total_equity,
            available_cash=account.available_cash,
            market_value=market_value,
            unrealized_pnl=position.unrealized_pnl,
        )

        return {
            "execution": execution,
            "trade": trade,
            "position": position,
            "cash_flow": cash_flow,
            "market_value": market_value,
        }

    def _build_fill_response(
        self,
        *,
        order: Order,
        trade: Trade,
        position: Position,
        account: Account,
        cash_flow: CashFlow,
        market_value: Decimal,
        execution: dict[str, object],
        risk_checks: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "status": "accepted",
            "risk_checks": risk_checks,
            "execution": execution,
            "order": {
                "id": order.id,
                "symbol": order.symbol,
                "quantity": order.quantity,
                "price": float(order.price),
                "status": order.status.value,
            },
            "trade": {
                "id": trade.id,
                "symbol": trade.symbol,
                "quantity": trade.quantity,
                "price": float(trade.price),
                "fee": float(trade.fee),
                "realized_pnl": float(trade.realized_pnl),
            },
            "position": {
                "id": position.id,
                "symbol": position.symbol,
                "quantity": position.quantity,
                "average_cost": float(position.average_cost),
                "market_value": float(market_value),
            },
            "account": {
                "id": account.id,
                "available_cash": float(account.available_cash),
                "total_equity": float(account.total_equity),
            },
            "cash_flow": {
                "flow_type": cash_flow.flow_type.value,
                "amount": float(cash_flow.amount),
                "balance_after": float(cash_flow.balance_after),
            },
        }

    def _validate_for_execution(
        self,
        db: Session,
        *,
        account: Account,
        position: Position | None,
        side: Literal["buy", "sell"],
        quantity: int,
        price_decimal: Decimal,
        current_position_value: Decimal,
        total_position_value: Decimal,
        quote: dict[str, float | bool],
    ) -> dict[str, object]:
        if side == "buy":
            return self.risk_service.validate_order(
                quantity=quantity,
                price=float(price_decimal),
                available_cash=float(account.available_cash),
                total_equity=float(account.total_equity),
                current_position_value=float(current_position_value),
                total_position_value=float(total_position_value),
                daily_trade_count=self._daily_trade_count(db, account.id),
                is_halted=quote["is_halted"],
                is_limit_up=quote["change_percent"] >= 9.9,
                is_limit_down=False,
            )

        if position is None or position.available_quantity < quantity:
            return {"passed": False, "checks": [], "rejection_reason": "insufficient position"}
        if position.last_buy_date == market_trade_date():
            return {"passed": False, "checks": [], "rejection_reason": "t+1 sell restriction"}
        return self.risk_service.validate_order(
            quantity=quantity,
            price=float(price_decimal),
            available_cash=float(account.available_cash),
            total_equity=float(account.total_equity),
            current_position_value=float(current_position_value),
            total_position_value=float(total_position_value),
            daily_trade_count=self._daily_trade_count(db, account.id),
            is_halted=quote["is_halted"],
            is_limit_up=False,
            is_limit_down=quote["change_percent"] <= -9.9,
            is_sell=True,
        )

    def _get_default_account(self, db: Session) -> Account | None:
        return db.scalar(
            select(Account).where(
                Account.tenant_id == settings.default_tenant_id,
                Account.name == settings.default_account_name,
            )
        )

    def _get_position(self, db: Session, account_id: int, symbol: str) -> Position | None:
        return db.scalar(
            select(Position).where(
                Position.account_id == account_id,
                Position.symbol == symbol,
            )
        )

    def _daily_trade_count(self, db: Session, account_id: int) -> int:
        today = market_trade_date()
        return db.scalar(
            select(func.count(Trade.id)).where(
                Trade.account_id == account_id,
                func.date(Trade.executed_at) == today,
            )
        ) or 0

    def _get_quote_snapshot(self, symbol: str) -> dict[str, float | bool]:
        quotes = self.quote_service.list_quotes([symbol])
        quote = quotes[0] if quotes else None
        return {
            "price": quote.price if quote is not None else 0.0,
            "change_percent": quote.change_percent if quote is not None else 0.0,
            "is_halted": quote.is_halted if quote is not None else False,
        }

    def _total_position_value_query(self, account_id: int) -> Select[tuple[Decimal | None]]:
        return select(func.coalesce(func.sum(Position.quantity * Position.last_price), 0)).where(Position.account_id == account_id)

    @staticmethod
    def _to_decimal(value: float | int, quantum: Decimal) -> Decimal:
        return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
