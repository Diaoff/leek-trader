from datetime import datetime

from app.core.trading_calendar import is_trading_time
from app.schemas.risk import RiskCheckResult, RiskDecision, RiskEvaluationResult, RiskSeverity
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
    ) -> RiskEvaluationResult:
        checks: list[RiskCheckResult] = []
        trading_time_ok = self._is_trading_time() if is_trading_time is None else is_trading_time

        checks.append(self._check("check_trading_time", trading_time_ok, "outside trading hours", True, trading_time_ok, risk_rule_version=risk_rule_version))
        checks.append(self._check("check_symbol_status", not is_halted, "symbol halted", False, is_halted, risk_rule_version=risk_rule_version))
        checks.append(self._check("check_daily_trade_limit", daily_trade_count < max_daily_trades, "daily trade limit exceeded", max_daily_trades, daily_trade_count, risk_rule_version=risk_rule_version))

        if not is_sell:
            projected_position_value = current_position_value + quantity * price
            position_threshold = total_equity * single_position_limit_pct
            checks.append(
                self._check(
                    "check_position_limit",
                    projected_position_value <= position_threshold,
                    "single position limit exceeded",
                    position_threshold,
                    projected_position_value,
                    metadata={"limit_pct": single_position_limit_pct},
                    risk_rule_version=risk_rule_version,
                )
            )

            projected_total_position = total_position_value + quantity * price
            exposure_threshold = total_equity * total_exposure_limit_pct
            checks.append(
                self._check(
                    "check_total_exposure_limit",
                    projected_total_position <= exposure_threshold,
                    "total exposure limit exceeded",
                    exposure_threshold,
                    projected_total_position,
                    metadata={"limit_pct": total_exposure_limit_pct},
                    risk_rule_version=risk_rule_version,
                )
            )
            near_position_threshold = position_threshold * 0.9
            checks.append(
                RiskCheckResult(
                    rule_id="warn_near_single_position_limit",
                    passed=True,
                    severity=RiskSeverity.WARN,
                    suggested_action="review_position_size",
                    explanation="approaching single position limit",
                    threshold=near_position_threshold,
                    actual=projected_position_value,
                    metadata={"limit_pct": single_position_limit_pct, "triggered": projected_position_value >= near_position_threshold},
                    rule_version=risk_rule_version,
                )
            )
        checks.append(self._check("check_daily_loss_circuit_breaker", daily_loss_rate < daily_loss_limit_pct, "daily loss circuit breaker triggered", daily_loss_limit_pct, daily_loss_rate, risk_rule_version=risk_rule_version))

        required_cash = quantity * price
        if not is_sell and available_cash < required_cash:
            checks.append(self._check("check_available_cash", False, "insufficient cash", required_cash, available_cash, risk_rule_version=risk_rule_version))
        if is_limit_up:
            checks.append(self._check("check_limit_up", False, "symbol at limit up", 9.9, 9.9, risk_rule_version=risk_rule_version))
        if is_limit_down:
            checks.append(self._check("check_limit_down", False, "symbol at limit down", -9.9, -9.9, risk_rule_version=risk_rule_version))

        rejection = next((item.explanation for item in checks if not item.passed and item.severity == RiskSeverity.HARD), None)
        warning_triggered = any(item.is_triggered_warning() for item in checks)
        return RiskEvaluationResult(
            passed=rejection is None,
            decision=RiskDecision.REJECT if rejection is not None else (RiskDecision.WARN if warning_triggered else RiskDecision.PASS),
            checks=checks,
            rejection_reason=rejection,
            risk_rule_version=risk_rule_version,
        )

    @staticmethod
    def _is_trading_time(now: datetime | None = None) -> bool:
        return is_trading_time(now)

    @staticmethod
    def _check(
        rule_id: str,
        passed: bool,
        explanation: str,
        threshold: bool | int | float,
        actual: bool | int | float,
        *,
        metadata: dict | None = None,
        risk_rule_version: str | None = None,
    ) -> RiskCheckResult:
        return RiskCheckResult(
            rule_id=rule_id,
            passed=passed,
            severity=RiskSeverity.HARD,
            suggested_action="block_order" if not passed else "continue",
            explanation=explanation if not passed else None,
            threshold=threshold,
            actual=actual,
            metadata=metadata or {},
            rule_version=risk_rule_version,
        )
