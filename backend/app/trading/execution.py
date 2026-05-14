from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.trading.reason_codes import display_reason, normalize_reason_code


DEFAULT_A_SHARE_LOT_SIZE = 100


@dataclass(frozen=True, slots=True)
class ExecutionOrderIntent:
    symbol: str
    side: str
    requested_quantity: int
    price_reference: float
    mode: str = "paper"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionFill:
    symbol: str
    side: str
    requested_quantity: int
    filled_quantity: int
    unfilled_quantity: int
    price: float
    fee: float = 0.0
    matched: bool = True
    mode: str = "paper"
    reject_reason: str | None = None
    rejection_code: str | None = None

    @classmethod
    def from_intent(
        cls,
        intent: ExecutionOrderIntent,
        *,
        filled_quantity: int,
        price: float | None = None,
        fee: float = 0.0,
        matched: bool | None = None,
        reject_reason: str | None = None,
        rejection_code: str | None = None,
    ) -> "ExecutionFill":
        normalized_filled = max(int(filled_quantity), 0)
        return cls(
            symbol=intent.symbol,
            side=intent.side,
            requested_quantity=max(int(intent.requested_quantity), 0),
            filled_quantity=normalized_filled,
            unfilled_quantity=calculate_unfilled_quantity(intent.requested_quantity, normalized_filled),
            price=float(intent.price_reference if price is None else price),
            fee=float(fee),
            matched=normalized_filled > 0 if matched is None else matched,
            mode=intent.mode,
            reject_reason=reject_reason,
            rejection_code=rejection_code,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if payload["rejection_code"] is None and payload["reject_reason"] is not None:
            payload["rejection_code"] = normalize_reason_code(payload["reject_reason"])
        if payload["reject_reason"] is None and payload["rejection_code"] is not None:
            payload["reject_reason"] = display_reason(payload["rejection_code"])
        return payload


FOUR_DP_DECIMAL = Decimal("0.0001")
TWO_DP_DECIMAL = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ExecutionCostBreakdown:
    trade_value: Decimal
    commission: Decimal
    stamp_tax: Decimal
    total_fee: Decimal

    def to_dict(self) -> dict[str, float]:
        return {
            "trade_value": float(self.trade_value),
            "commission": float(self.commission),
            "stamp_tax": float(self.stamp_tax),
            "total_fee": float(self.total_fee),
        }


def calculate_execution_cost(
    *,
    quantity: int,
    price: float | Decimal,
    side: str,
    commission_rate: float,
    min_commission: float,
    stamp_tax_rate: float,
) -> ExecutionCostBreakdown:
    normalized_quantity = max(int(quantity), 0)
    normalized_price = Decimal(str(price)).quantize(FOUR_DP_DECIMAL, rounding=ROUND_HALF_UP)
    trade_value = (Decimal(normalized_quantity) * normalized_price).quantize(TWO_DP_DECIMAL, rounding=ROUND_HALF_UP)
    return calculate_execution_cost_from_trade_value(
        trade_value=trade_value,
        side=side,
        commission_rate=commission_rate,
        min_commission=min_commission,
        stamp_tax_rate=stamp_tax_rate,
    )


def calculate_execution_cost_from_trade_value(
    *,
    trade_value: Decimal,
    side: str,
    commission_rate: float,
    min_commission: float,
    stamp_tax_rate: float,
) -> ExecutionCostBreakdown:
    normalized_trade_value = Decimal(str(trade_value)).quantize(TWO_DP_DECIMAL, rounding=ROUND_HALF_UP)
    commission = normalized_trade_value * Decimal(str(commission_rate))
    if commission > 0:
        commission = max(commission, Decimal(str(min_commission)))
    commission = commission.quantize(TWO_DP_DECIMAL, rounding=ROUND_HALF_UP)
    stamp_tax = Decimal("0.00")
    if side == "sell":
        stamp_tax = (normalized_trade_value * Decimal(str(stamp_tax_rate))).quantize(TWO_DP_DECIMAL, rounding=ROUND_HALF_UP)
    total_fee = (commission + stamp_tax).quantize(TWO_DP_DECIMAL, rounding=ROUND_HALF_UP)
    return ExecutionCostBreakdown(
        trade_value=normalized_trade_value,
        commission=commission,
        stamp_tax=stamp_tax,
        total_fee=total_fee,
    )


def normalize_lot_quantity(quantity: int, *, lot_size: int = DEFAULT_A_SHARE_LOT_SIZE, minimum_lot: bool = False) -> int:
    normalized_quantity = max(int(quantity), 0)
    if lot_size <= 0:
        return normalized_quantity
    normalized_quantity = (normalized_quantity // lot_size) * lot_size
    if minimum_lot and quantity > 0 and normalized_quantity == 0:
        return lot_size
    return normalized_quantity


def calculate_unfilled_quantity(requested_quantity: int, filled_quantity: int) -> int:
    return max(int(requested_quantity) - int(filled_quantity), 0)
