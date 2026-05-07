from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.trading_calendar import market_trade_date, previous_trading_day
from app.market.service import QuoteService
from app.models.account import Account
from app.models.cash_flow import CashFlow, CashFlowType
from app.models.order import Order, OrderSide, OrderStatus, OrderType
from app.models.position import Position
from app.models.strategy import Strategy, StrategyStatus
from app.models.trade import Trade
from app.models.watchlist import WatchlistItem
from app.preferences.service import PreferenceService
from app.reporting.service import ReportingService
from app.risk.service import RiskService
from app.trading.matcher import TradeMatcher


FOUR_DP = Decimal("0.0001")
TWO_DP = Decimal("0.01")
EXIT_GUARD_STATUS_INACTIVE = "inactive"
EXIT_GUARD_STATUS_ACTIVE = "active"
EXIT_GUARD_STATUS_TRIGGERED = "triggered"


class TradingService:
    def __init__(self, quote_service: QuoteService | None = None, reporting_service: ReportingService | None = None) -> None:
        self.risk_service = RiskService()
        self.matcher = TradeMatcher()
        self.quote_service = quote_service or QuoteService()
        self.reporting_service = reporting_service or ReportingService()
        self.preference_service = PreferenceService()

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
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        strategy_add_increment: bool = False,
        exit_trigger_reason: str | None = None,
    ) -> dict[str, object]:
        normalized_quantity = max((quantity // 100) * 100, 100)
        price_decimal = self._to_decimal(price, FOUR_DP)
        order_side = OrderSide(side)
        order_kind = OrderType(order_type)
        note_prefix = note_prefix or f"order {side}"

        account = self._get_default_account(db)
        if account is None:
            raise RuntimeError("default account not initialized")
        self.unlock_settled_positions(db, account.id)

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
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            strategy_add_increment=strategy_add_increment,
            exit_trigger_reason=exit_trigger_reason,
        )
        db.commit()
        db.refresh(order)
        db.refresh(payload["trade"])
        db.refresh(payload["position"])
        db.refresh(account)

        return self._build_fill_response(order=order, account=account, risk_checks=risk_result["checks"], **payload)

    def update_position_exit_guard(
        self,
        db: Session,
        *,
        position_id: int,
        stop_loss_price: float | None,
        take_profit_price: float | None,
    ) -> Position | None:
        account = self._get_default_account(db)
        if account is None:
            raise RuntimeError("default account not initialized")

        position = db.scalar(
            select(Position).where(
                Position.id == position_id,
                Position.account_id == account.id,
                Position.quantity > 0,
            )
        )
        if position is None:
            return None

        self._set_position_exit_guard(
            position,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )
        db.add(position)
        db.commit()
        db.refresh(position)
        return position

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
                stop_loss_price=None,
                take_profit_price=None,
                strategy_add_increment=False,
                exit_trigger_reason=None,
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

    def monitor_position_guards(self, db: Session) -> dict[str, object]:
        account = self._get_default_account(db)
        if account is not None:
            self.unlock_settled_positions(db, account.id)

        positions = db.scalars(
            select(Position)
            .where(
                Position.quantity > 0,
                Position.exit_guard_status == EXIT_GUARD_STATUS_ACTIVE,
                or_(
                    Position.stop_loss_price.is_not(None),
                    Position.take_profit_price.is_not(None),
                ),
            )
            .order_by(Position.updated_at.asc(), Position.id.asc())
        ).all()

        triggered_orders: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        for position in positions:
            if position.available_quantity < 100:
                skipped.append({"symbol": position.symbol, "reason": "insufficient_available_quantity"})
                continue
            if self._has_pending_sell_order(db, position.account_id, position.symbol):
                skipped.append({"symbol": position.symbol, "reason": "pending_exit_order"})
                continue

            quote = self._get_quote_snapshot(position.symbol)
            latest_price = self._to_decimal(float(quote.get("price") or 0.0), FOUR_DP)
            if latest_price <= 0:
                skipped.append({"symbol": position.symbol, "reason": "quote_unavailable"})
                continue
            trigger_reason = self._resolve_exit_trigger_reason(position, latest_price)
            if trigger_reason is None:
                continue

            sell_quantity = (position.available_quantity // 100) * 100
            if sell_quantity < 100:
                skipped.append({"symbol": position.symbol, "reason": "quantity_below_min_lot"})
                continue

            order_result = self.place_order(
                db,
                symbol=position.symbol,
                side="sell",
                order_type="market",
                quantity=sell_quantity,
                price=float(latest_price),
                note_prefix=f"guard {trigger_reason}",
                exit_trigger_reason=trigger_reason,
            )
            order_payload = order_result.get("order", {})
            accepted = bool(order_result.get("status") == "accepted" and order_payload.get("status") != "rejected")
            if accepted:
                triggered_orders.append(
                    {
                        "symbol": position.symbol,
                        "reason": trigger_reason,
                        "order_id": order_payload.get("id"),
                        "quantity": order_payload.get("quantity"),
                        "price": order_payload.get("price"),
                    }
                )
                continue

            skipped.append(
                {
                    "symbol": position.symbol,
                    "reason": order_result.get("rejection_reason") or order_payload.get("reject_reason") or "order_rejected",
                }
            )

        return {
            "status": "accepted",
            "scanned_count": len(positions),
            "triggered_count": len(triggered_orders),
            "triggered_orders": triggered_orders,
            "skipped": skipped,
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
        stop_loss_price: float | None,
        take_profit_price: float | None,
        strategy_add_increment: bool,
        exit_trigger_reason: str | None,
    ) -> dict[str, object]:
        normalized_quantity = order.quantity
        trade_value = self._to_decimal(normalized_quantity, FOUR_DP) * price_decimal
        fee = self._calculate_trade_fee(db, trade_value=trade_value, side=side)
        execution = self.matcher.match(order.symbol, normalized_quantity, float(price_decimal))

        if side == "buy":
            cash_after = (account.available_cash - trade_value - fee).quantize(TWO_DP, rounding=ROUND_HALF_UP)
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
                    stop_loss_price=None,
                    take_profit_price=None,
                    strategy_add_count=0,
                    exit_guard_status=EXIT_GUARD_STATUS_INACTIVE,
                    exit_trigger_reason=None,
                    exit_triggered_at=None,
                    last_buy_date=trade_date,
                )
                db.add(position)
                db.flush()

            total_cost_before = position.average_cost * position.quantity
            new_total_quantity = position.quantity + normalized_quantity
            new_total_cost = total_cost_before + trade_value + fee
            position.quantity = new_total_quantity
            position.average_cost = (new_total_cost / Decimal(new_total_quantity)).quantize(FOUR_DP, rounding=ROUND_HALF_UP)
            position.last_price = price_decimal
            position.unrealized_pnl = Decimal("0.00")
            position.last_buy_date = trade_date
            if strategy_add_increment:
                position.strategy_add_count += 1
            if stop_loss_price is not None or take_profit_price is not None:
                self._set_position_exit_guard(
                    position,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price,
                )
            cash_flow_amount = (-(trade_value + fee)).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        else:
            assert position is not None
            realized_pnl = (
                (price_decimal - position.average_cost) * Decimal(normalized_quantity) - fee
            ).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            cash_after = (account.available_cash + trade_value - fee).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            new_quantity = position.quantity - normalized_quantity
            position.quantity = new_quantity
            position.available_quantity = max(position.available_quantity - normalized_quantity, 0)
            position.realized_pnl = (position.realized_pnl + realized_pnl).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            position.last_price = price_decimal
            if exit_trigger_reason is not None:
                position.exit_guard_status = EXIT_GUARD_STATUS_TRIGGERED
                position.exit_trigger_reason = exit_trigger_reason
                position.exit_triggered_at = datetime.utcnow()
            if new_quantity == 0:
                position.average_cost = Decimal("0.0000")
                position.last_price = Decimal("0.0000")
                position.unrealized_pnl = Decimal("0.00")
                position.available_quantity = 0
                position.strategy_add_count = 0
                self._clear_position_exit_guard(position)
            cash_flow_amount = (trade_value - fee).quantize(TWO_DP, rounding=ROUND_HALF_UP)

        trade = Trade(
            tenant_id=account.tenant_id,
            account_id=account.id,
            order_id=order.id,
            symbol=order.symbol,
            quantity=normalized_quantity,
            price=price_decimal,
            fee=fee,
            realized_pnl=realized_pnl,
        )
        db.add(trade)

        market_value = (Decimal(position.quantity) * position.last_price).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        account.available_cash = cash_after
        account.total_equity = (cash_after + account.frozen_cash + market_value).quantize(TWO_DP, rounding=ROUND_HALF_UP)

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
            trade_value = Decimal(quantity) * price_decimal
            fee_estimate = self._calculate_trade_fee(db, trade_value=trade_value, side=side)
            effective_price = (price_decimal + (fee_estimate / Decimal(quantity))).quantize(
                FOUR_DP,
                rounding=ROUND_HALF_UP,
            )
            return self.risk_service.validate_order(
                quantity=quantity,
                price=float(effective_price),
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

    @staticmethod
    def unlock_settled_positions(db: Session, account_id: int) -> None:
        trade_date = market_trade_date()
        positions = db.scalars(
            select(Position).where(
                Position.account_id == account_id,
                Position.quantity > 0,
                Position.available_quantity < Position.quantity,
                or_(Position.last_buy_date.is_(None), Position.last_buy_date <= previous_trading_day(trade_date)),
            )
        ).all()
        for position in positions:
            position.available_quantity = position.quantity
        if positions:
            db.flush()

    def _get_default_account(self, db: Session) -> Account | None:
        return db.scalar(
            select(Account).where(
                Account.tenant_id == settings.default_tenant_id,
                Account.name == settings.default_account_name,
            )
        )

    def _calculate_trade_fee(self, db: Session, *, trade_value: Decimal, side: Literal["buy", "sell"]) -> Decimal:
        preferences = self.preference_service.trading_preferences(db=db)
        commission = trade_value * Decimal(str(preferences.commission_rate))
        if commission > 0:
            commission = max(commission, Decimal(str(preferences.min_commission)))
        stamp_tax = Decimal("0.00")
        if side == "sell":
            stamp_tax = trade_value * Decimal(str(preferences.stamp_tax_rate))
        return (commission + stamp_tax).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    def _get_position(self, db: Session, account_id: int, symbol: str) -> Position | None:
        return db.scalar(
            select(Position).where(
                Position.account_id == account_id,
                Position.symbol == symbol,
            )
        )

    @staticmethod
    def _set_position_exit_guard(
        position: Position,
        *,
        stop_loss_price: float | None,
        take_profit_price: float | None,
    ) -> None:
        position.stop_loss_price = (
            TradingService._to_decimal(stop_loss_price, FOUR_DP)
            if stop_loss_price is not None
            else None
        )
        position.take_profit_price = (
            TradingService._to_decimal(take_profit_price, FOUR_DP)
            if take_profit_price is not None
            else None
        )
        if position.stop_loss_price is None and position.take_profit_price is None:
            position.exit_guard_status = EXIT_GUARD_STATUS_INACTIVE
            position.exit_trigger_reason = None
            position.exit_triggered_at = None
            return
        position.exit_guard_status = EXIT_GUARD_STATUS_ACTIVE
        position.exit_trigger_reason = None
        position.exit_triggered_at = None

    @staticmethod
    def _clear_position_exit_guard(position: Position) -> None:
        position.stop_loss_price = None
        position.take_profit_price = None
        position.exit_guard_status = EXIT_GUARD_STATUS_INACTIVE
        position.exit_trigger_reason = None
        position.exit_triggered_at = None

    @staticmethod
    def _resolve_exit_trigger_reason(position: Position, latest_price: Decimal) -> str | None:
        if position.stop_loss_price is not None and latest_price <= position.stop_loss_price:
            return "stop_loss"
        if position.take_profit_price is not None and latest_price >= position.take_profit_price:
            return "take_profit"
        return None

    @staticmethod
    def _has_pending_sell_order(db: Session, account_id: int, symbol: str) -> bool:
        pending_order_id = db.scalar(
            select(Order.id)
            .where(
                Order.account_id == account_id,
                Order.symbol == symbol,
                Order.side == OrderSide.SELL,
                Order.status == OrderStatus.PENDING,
            )
            .limit(1)
        )
        return pending_order_id is not None

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
