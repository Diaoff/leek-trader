from __future__ import annotations

from typing import Any


SUSPENDED = "suspended"
T_PLUS_ONE_SELL_BLOCKED = "t_plus_one_sell_blocked"
LIMIT_UP_BUY_BLOCKED = "limit_up_buy_blocked"
LIMIT_DOWN_SELL_BLOCKED = "limit_down_sell_blocked"
INSUFFICIENT_POSITION = "insufficient_position"
INSUFFICIENT_CASH = "insufficient_cash"
OUTSIDE_TRADING_HOURS = "outside_trading_hours"
MODEL_HOLD_OR_ZERO_TARGET = "model_hold_or_zero_target"
HOLD_SIGNAL = "hold_signal"
MIN_CONFIDENCE_NOT_MET = "min_confidence_not_met"
ZERO_TARGET_POSITION = "zero_target_position"
TARGET_DELTA_TOO_SMALL = "target_delta_too_small"
NO_POSITION_TO_EXIT = "no_position_to_exit"
NO_REBALANCE_NEEDED = "no_rebalance_needed"
INSUFFICIENT_CASH_OR_LOT = "insufficient_cash_or_lot"
DAILY_TRADE_LIMIT_EXCEEDED = "daily_trade_limit_exceeded"
SINGLE_POSITION_LIMIT_EXCEEDED = "single_position_limit_exceeded"
TOTAL_EXPOSURE_LIMIT_EXCEEDED = "total_exposure_limit_exceeded"
DAILY_LOSS_CIRCUIT_BREAKER = "daily_loss_circuit_breaker"
ORDER_REJECTED = "order_rejected"

REASON_CODE_BY_VALUE = {
    None: None,
    SUSPENDED: SUSPENDED,
    "symbol halted": SUSPENDED,
    OUTSIDE_TRADING_HOURS: OUTSIDE_TRADING_HOURS,
    "outside trading hours": OUTSIDE_TRADING_HOURS,
    INSUFFICIENT_CASH: INSUFFICIENT_CASH,
    "insufficient cash": INSUFFICIENT_CASH,
    INSUFFICIENT_POSITION: INSUFFICIENT_POSITION,
    "insufficient position": INSUFFICIENT_POSITION,
    T_PLUS_ONE_SELL_BLOCKED: T_PLUS_ONE_SELL_BLOCKED,
    "t+1 sell restriction": T_PLUS_ONE_SELL_BLOCKED,
    "t_plus_one_restriction": T_PLUS_ONE_SELL_BLOCKED,
    LIMIT_UP_BUY_BLOCKED: LIMIT_UP_BUY_BLOCKED,
    "symbol at limit up": LIMIT_UP_BUY_BLOCKED,
    "limit_up_restriction": LIMIT_UP_BUY_BLOCKED,
    LIMIT_DOWN_SELL_BLOCKED: LIMIT_DOWN_SELL_BLOCKED,
    "symbol at limit down": LIMIT_DOWN_SELL_BLOCKED,
    "limit_down_restriction": LIMIT_DOWN_SELL_BLOCKED,
    MODEL_HOLD_OR_ZERO_TARGET: MODEL_HOLD_OR_ZERO_TARGET,
    HOLD_SIGNAL: HOLD_SIGNAL,
    "hold signal": HOLD_SIGNAL,
    MIN_CONFIDENCE_NOT_MET: MIN_CONFIDENCE_NOT_MET,
    "minimum confidence not met": MIN_CONFIDENCE_NOT_MET,
    ZERO_TARGET_POSITION: ZERO_TARGET_POSITION,
    "zero target position": ZERO_TARGET_POSITION,
    TARGET_DELTA_TOO_SMALL: TARGET_DELTA_TOO_SMALL,
    "target delta too small": TARGET_DELTA_TOO_SMALL,
    NO_POSITION_TO_EXIT: NO_POSITION_TO_EXIT,
    "no position to exit": NO_POSITION_TO_EXIT,
    NO_REBALANCE_NEEDED: NO_REBALANCE_NEEDED,
    "no rebalance needed": NO_REBALANCE_NEEDED,
    INSUFFICIENT_CASH_OR_LOT: INSUFFICIENT_CASH_OR_LOT,
    "insufficient cash or lot": INSUFFICIENT_CASH_OR_LOT,
    DAILY_TRADE_LIMIT_EXCEEDED: DAILY_TRADE_LIMIT_EXCEEDED,
    "daily trade limit exceeded": DAILY_TRADE_LIMIT_EXCEEDED,
    SINGLE_POSITION_LIMIT_EXCEEDED: SINGLE_POSITION_LIMIT_EXCEEDED,
    "single position limit exceeded": SINGLE_POSITION_LIMIT_EXCEEDED,
    TOTAL_EXPOSURE_LIMIT_EXCEEDED: TOTAL_EXPOSURE_LIMIT_EXCEEDED,
    "total exposure limit exceeded": TOTAL_EXPOSURE_LIMIT_EXCEEDED,
    DAILY_LOSS_CIRCUIT_BREAKER: DAILY_LOSS_CIRCUIT_BREAKER,
    "daily loss circuit breaker triggered": DAILY_LOSS_CIRCUIT_BREAKER,
    ORDER_REJECTED: ORDER_REJECTED,
    "order_rejected": ORDER_REJECTED,
}

DISPLAY_REASON_BY_CODE = {
    SUSPENDED: "symbol halted",
    OUTSIDE_TRADING_HOURS: "outside trading hours",
    INSUFFICIENT_CASH: "insufficient cash",
    INSUFFICIENT_POSITION: "insufficient position",
    T_PLUS_ONE_SELL_BLOCKED: "t+1 sell restriction",
    LIMIT_UP_BUY_BLOCKED: "symbol at limit up",
    LIMIT_DOWN_SELL_BLOCKED: "symbol at limit down",
    MODEL_HOLD_OR_ZERO_TARGET: "model hold or zero target",
    HOLD_SIGNAL: "hold signal",
    MIN_CONFIDENCE_NOT_MET: "minimum confidence not met",
    ZERO_TARGET_POSITION: "zero target position",
    TARGET_DELTA_TOO_SMALL: "target delta too small",
    NO_POSITION_TO_EXIT: "no position to exit",
    NO_REBALANCE_NEEDED: "no rebalance needed",
    INSUFFICIENT_CASH_OR_LOT: "insufficient cash or lot",
    DAILY_TRADE_LIMIT_EXCEEDED: "daily trade limit exceeded",
    SINGLE_POSITION_LIMIT_EXCEEDED: "single position limit exceeded",
    TOTAL_EXPOSURE_LIMIT_EXCEEDED: "total exposure limit exceeded",
    DAILY_LOSS_CIRCUIT_BREAKER: "daily loss circuit breaker triggered",
    ORDER_REJECTED: "order rejected",
}


def normalize_reason_code(value: Any) -> str | None:
    if value in REASON_CODE_BY_VALUE:
        return REASON_CODE_BY_VALUE[value]
    if value is None:
        return None
    text = str(value)
    return REASON_CODE_BY_VALUE.get(text, text)


def display_reason(value: Any) -> str | None:
    code = normalize_reason_code(value)
    if code is None:
        return None
    return DISPLAY_REASON_BY_CODE.get(code, str(value) if value is not None else None)


STANDARD_REASON_CODES = {
    SUSPENDED,
    T_PLUS_ONE_SELL_BLOCKED,
    LIMIT_UP_BUY_BLOCKED,
    LIMIT_DOWN_SELL_BLOCKED,
    INSUFFICIENT_POSITION,
    INSUFFICIENT_CASH,
    OUTSIDE_TRADING_HOURS,
    MODEL_HOLD_OR_ZERO_TARGET,
    HOLD_SIGNAL,
    MIN_CONFIDENCE_NOT_MET,
    ZERO_TARGET_POSITION,
    TARGET_DELTA_TOO_SMALL,
    NO_POSITION_TO_EXIT,
    NO_REBALANCE_NEEDED,
    INSUFFICIENT_CASH_OR_LOT,
}
