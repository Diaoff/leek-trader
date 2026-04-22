from datetime import datetime, time

ORDER_RISK_CHECKS = [
    "check_trading_time",
    "check_symbol_status",
    "check_daily_trade_limit",
    "check_position_limit",
    "check_total_exposure_limit",
    "check_daily_loss_circuit_breaker",
]


class RiskService:
    def validate_order(
        self,
        *,
        quantity: int,
        price: float,
        available_cash: float,
        total_equity: float,
        current_position_value: float,
        total_position_value: float,
        is_halted: bool = False,
        is_limit_up: bool = False,
        is_limit_down: bool = False,
        is_trading_time: bool | None = None,
        daily_trade_count: int = 0,
        daily_loss_rate: float = 0.0,
    ) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        trading_time_ok = self._is_trading_time() if is_trading_time is None else is_trading_time

        checks.append({
            "name": "check_trading_time",
            "passed": trading_time_ok,
            "reason": None if trading_time_ok else "outside trading hours",
        })
        checks.append({
            "name": "check_symbol_status",
            "passed": not is_halted,
            "reason": None if not is_halted else "symbol halted",
        })
        checks.append({
            "name": "check_daily_trade_limit",
            "passed": daily_trade_count < 20,
            "reason": None if daily_trade_count < 20 else "daily trade limit exceeded",
        })

        projected_position_value = current_position_value + quantity * price
        checks.append({
            "name": "check_position_limit",
            "passed": projected_position_value <= total_equity * 0.2,
            "reason": None if projected_position_value <= total_equity * 0.2 else "single position limit exceeded",
        })

        projected_total_position = total_position_value + quantity * price
        checks.append({
            "name": "check_total_exposure_limit",
            "passed": projected_total_position <= total_equity * 0.9,
            "reason": None if projected_total_position <= total_equity * 0.9 else "total exposure limit exceeded",
        })
        checks.append({
            "name": "check_daily_loss_circuit_breaker",
            "passed": daily_loss_rate < 0.05,
            "reason": None if daily_loss_rate < 0.05 else "daily loss circuit breaker triggered",
        })

        if available_cash < quantity * price:
            checks.append({"name": "check_available_cash", "passed": False, "reason": "insufficient cash"})
        if is_limit_up:
            checks.append({"name": "check_limit_up", "passed": False, "reason": "symbol at limit up"})
        if is_limit_down:
            checks.append({"name": "check_limit_down", "passed": False, "reason": "symbol at limit down"})

        rejection = next((item["reason"] for item in checks if not item["passed"]), None)
        return {
            "passed": rejection is None,
            "checks": checks,
            "rejection_reason": rejection,
        }

    @staticmethod
    def _is_trading_time(now: datetime | None = None) -> bool:
        current = now or datetime.now()
        current_time = current.time()
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)
        return morning_start <= current_time <= morning_end or afternoon_start <= current_time <= afternoon_end
