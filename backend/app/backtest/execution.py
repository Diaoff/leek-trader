from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.market.providers.base import DailyBarSnapshot
from app.trading.reason_codes import LIMIT_DOWN_SELL_BLOCKED, LIMIT_UP_BUY_BLOCKED, SUSPENDED, T_PLUS_ONE_SELL_BLOCKED
from app.trading.execution import DEFAULT_A_SHARE_LOT_SIZE, ExecutionOrderIntent, normalize_lot_quantity


@dataclass(frozen=True, slots=True)
class LimitMovePolicy:
    buy: Literal["reject", "defer"] = "reject"
    sell: Literal["reject", "defer"] = "reject"


@dataclass(frozen=True, slots=True)
class ExecutionModel:
    lot_size: int = DEFAULT_A_SHARE_LOT_SIZE
    max_volume_participation: float | None = None
    slippage_rate: float = 0.0
    fixed_slippage_amount: float = 0.0
    impact_slippage_factor: float = 0.0
    limit_move_policy: LimitMovePolicy = LimitMovePolicy()

    def to_dict(self) -> dict[str, Any]:
        return {
            "lot_size": self.lot_size,
            "max_volume_participation": self.max_volume_participation,
            "slippage_rate": self.slippage_rate,
            "fixed_slippage_amount": self.fixed_slippage_amount,
            "impact_slippage_factor": self.impact_slippage_factor,
            "limit_move_policy": {
                "buy": self.limit_move_policy.buy,
                "sell": self.limit_move_policy.sell,
            },
        }


def resolve_execution_model(parameters: dict[str, Any], *, slippage_rate: float = 0.0) -> ExecutionModel:
    raw_value = parameters.get("max_volume_participation")
    max_volume_participation: float | None
    if raw_value is None:
        max_volume_participation = None
    else:
        try:
            parsed = float(raw_value)
        except (TypeError, ValueError):
            parsed = 0.0
        max_volume_participation = min(parsed, 1.0) if parsed > 0 else None

    impact_slippage_factor = max(float(parameters.get("impact_slippage_factor") or 0.0), 0.0)
    fixed_slippage_amount = max(float(parameters.get("fixed_slippage_amount") or 0.0), 0.0)
    raw_policy = parameters.get("limit_move_policy")
    buy_policy = _coerce_policy(raw_policy.get("buy") if isinstance(raw_policy, dict) else None)
    sell_policy = _coerce_policy(raw_policy.get("sell") if isinstance(raw_policy, dict) else None)
    return ExecutionModel(
        max_volume_participation=max_volume_participation,
        slippage_rate=max(float(slippage_rate or 0.0), 0.0),
        fixed_slippage_amount=fixed_slippage_amount,
        impact_slippage_factor=impact_slippage_factor,
        limit_move_policy=LimitMovePolicy(buy=buy_policy, sell=sell_policy),
    )


def round_lot_shares(shares: int, *, lot_size: int = 100) -> int:
    return normalize_lot_quantity(shares, lot_size=lot_size)


def apply_volume_capacity(requested_shares: int, bar: DailyBarSnapshot, model: ExecutionModel) -> int:
    requested_shares = round_lot_shares(requested_shares, lot_size=model.lot_size)
    if requested_shares <= 0 or model.max_volume_participation is None:
        return requested_shares
    volume_capacity = round_lot_shares(
        int(float(bar.volume or 0.0) * model.max_volume_participation),
        lot_size=model.lot_size,
    )
    return min(requested_shares, max(volume_capacity, 0))


def apply_price_slippage(close_price: float, *, side: str, model: ExecutionModel) -> float:
    if side == "buy":
        return (close_price * (1 + model.slippage_rate)) + model.fixed_slippage_amount
    if side == "sell":
        return (close_price * (1 - model.slippage_rate)) - model.fixed_slippage_amount
    return close_price


def apply_impact_slippage(
    execution_price: float,
    bar: DailyBarSnapshot,
    *,
    shares: int,
    side: str,
    model: ExecutionModel,
) -> float:
    if model.impact_slippage_factor <= 0 or shares <= 0 or not bar.volume:
        return execution_price
    participation = min(shares / float(bar.volume), 1.0)
    impact = participation * model.impact_slippage_factor
    if side == "buy":
        return execution_price * (1 + impact)
    if side == "sell":
        return execution_price * (1 - impact)
    return execution_price


def buy_block_reason(bar: DailyBarSnapshot, *, model: ExecutionModel) -> str | None:
    if bar.trade_status != 1:
        return SUSPENDED
    if is_limit_up(bar):
        return LIMIT_UP_BUY_BLOCKED
    return None


def sell_block_reason(bar: DailyBarSnapshot, *, sellable_shares: int, model: ExecutionModel) -> str | None:
    if bar.trade_status != 1:
        return SUSPENDED
    if sellable_shares <= 0:
        return T_PLUS_ONE_SELL_BLOCKED
    if is_limit_down(bar):
        return LIMIT_DOWN_SELL_BLOCKED
    return None


def is_limit_up(bar: DailyBarSnapshot) -> bool:
    if not bar.preclose or bar.preclose <= 0:
        return False
    limit_pct = price_limit_pct(bar)
    return float(bar.close_price) >= float(bar.preclose) * (1 + limit_pct - 0.001)


def is_limit_down(bar: DailyBarSnapshot) -> bool:
    if not bar.preclose or bar.preclose <= 0:
        return False
    limit_pct = price_limit_pct(bar)
    return float(bar.close_price) <= float(bar.preclose) * (1 - limit_pct + 0.001)


def price_limit_pct(bar: DailyBarSnapshot) -> float:
    return 0.05 if bar.is_st else 0.10


def build_order_intent(*, symbol: str, side: str, requested_quantity: int, price_reference: float, mode: str) -> ExecutionOrderIntent:
    return ExecutionOrderIntent(
        symbol=symbol,
        side=side,
        requested_quantity=max(int(requested_quantity), 0),
        price_reference=float(price_reference),
        mode=mode,
    )


def _coerce_policy(value: Any) -> Literal["reject", "defer"]:
    return "defer" if value == "defer" else "reject"
