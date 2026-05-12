from datetime import datetime

from app.core.trading_calendar import is_trading_time
from app.risk.versioning import RiskRuleVersionService


DEFAULT_MAX_DAILY_TRADES = 20
DEFAULT_SINGLE_POSITION_LIMIT_PCT = 0.2
DEFAULT_TOTAL_EXPOSURE_LIMIT_PCT = 0.9
DEFAULT_DAILY_LOSS_LIMIT_PCT = 0.05

ORDER_RISK_CHECKS = [
    "check_trading_time",
    "check_symbol_status",
    "check_daily_trade_limit",
    "check_position_limit",
    "check_total_exposure_limit",
    "check_daily_loss_circuit_breaker",
]


class RiskService:
    def __init__(self, rule_version_service: RiskRuleVersionService | None = None) -> None:
        self.rule_version_service = rule_version_service or RiskRuleVersionService()

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
        is_sell: bool = False,
        daily_trade_count: int = 0,
        daily_loss_rate: float = 0.0,
        max_daily_trades: int = DEFAULT_MAX_DAILY_TRADES,
        single_position_limit_pct: float = DEFAULT_SINGLE_POSITION_LIMIT_PCT,
        total_exposure_limit_pct: float = DEFAULT_TOTAL_EXPOSURE_LIMIT_PCT,
        daily_loss_limit_pct: float = DEFAULT_DAILY_LOSS_LIMIT_PCT,
        risk_rule_version: str | None = None,
    ) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        trading_time_ok = self._is_trading_time() if is_trading_time is None else is_trading_time

        checks.append({
            "name": "check_trading_time",
            "passed": trading_time_ok,
            "reason": None if trading_time_ok else "outside trading hours",
            "threshold": True,
            "actual": trading_time_ok,
        })
        checks.append({
            "name": "check_symbol_status",
            "passed": not is_halted,
            "reason": None if not is_halted else "symbol halted",
            "threshold": False,
            "actual": is_halted,
        })
        checks.append({
            "name": "check_daily_trade_limit",
            "passed": daily_trade_count < max_daily_trades,
            "reason": None if daily_trade_count < max_daily_trades else "daily trade limit exceeded",
            "threshold": max_daily_trades,
            "actual": daily_trade_count,
        })

        if not is_sell:
            projected_position_value = current_position_value + quantity * price
            position_threshold = total_equity * single_position_limit_pct
            checks.append({
                "name": "check_position_limit",
                "passed": projected_position_value <= position_threshold,
                "reason": None if projected_position_value <= position_threshold else "single position limit exceeded",
                "threshold": position_threshold,
                "actual": projected_position_value,
                "limit_pct": single_position_limit_pct,
            })

            projected_total_position = total_position_value + quantity * price
            exposure_threshold = total_equity * total_exposure_limit_pct
            checks.append({
                "name": "check_total_exposure_limit",
                "passed": projected_total_position <= exposure_threshold,
                "reason": None if projected_total_position <= exposure_threshold else "total exposure limit exceeded",
                "threshold": exposure_threshold,
                "actual": projected_total_position,
                "limit_pct": total_exposure_limit_pct,
            })
        checks.append({
            "name": "check_daily_loss_circuit_breaker",
            "passed": daily_loss_rate < daily_loss_limit_pct,
            "reason": None if daily_loss_rate < daily_loss_limit_pct else "daily loss circuit breaker triggered",
            "threshold": daily_loss_limit_pct,
            "actual": daily_loss_rate,
        })

        required_cash = quantity * price
        if not is_sell and available_cash < required_cash:
            checks.append({
                "name": "check_available_cash",
                "passed": False,
                "reason": "insufficient cash",
                "threshold": required_cash,
                "actual": available_cash,
            })
        if is_limit_up:
            checks.append({
                "name": "check_limit_up",
                "passed": False,
                "reason": "symbol at limit up",
                "threshold": 9.9,
                "actual": 9.9,
            })
        if is_limit_down:
            checks.append({
                "name": "check_limit_down",
                "passed": False,
                "reason": "symbol at limit down",
                "threshold": -9.9,
                "actual": -9.9,
            })

        rejection = next((item["reason"] for item in checks if not item["passed"]), None)
        return {
            "passed": rejection is None,
            "checks": checks,
            "rejection_reason": rejection,
            "risk_rule_version": risk_rule_version,
        }

    @staticmethod
    def _is_trading_time(now: datetime | None = None) -> bool:
        return is_trading_time(now)
