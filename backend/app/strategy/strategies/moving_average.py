from __future__ import annotations

from app.market.providers.base import DailyBarSnapshot
from app.strategy.base import StrategyPlugin
from app.strategy.contracts import ParameterConstraint, StrategyMetadata, StrategySignal
from app.strategy.signals import signal_from_payload
from app.strategy.strategies.manager_style import ManagerStyleGate


class MovingAverageStrategy(StrategyPlugin):
    name = "moving_average"
    metadata = StrategyMetadata(
        strategy_type=name,
        display_name="双均线",
        template_category="breakout",
        minimum_history=30,
        supported_execution_modes=("signal_only", "auto_trade"),
        parameter_schema=(
            ParameterConstraint("short_window", "integer", minimum=2, default=5, description="短均线窗口"),
            ParameterConstraint("long_window", "integer", minimum=3, default=20, description="长均线窗口"),
            ParameterConstraint("position_pct", "number", minimum=0, maximum=1, default=0.1, description="最大仓位"),
        ),
        risk_note="震荡市容易来回打脸，需严格控制仓位与回撤",
        mode_note="适合趋势明确的纸面观察与自动纸面下单",
        auto_trade_allowed=True,
    )

    def minimum_history(self, parameters: dict[str, object]) -> int:
        short_window = max(int(parameters.get("short_window", 5)), 2)
        long_window = max(int(parameters.get("long_window", 20)), short_window + 1)
        return max(long_window + 10, self.metadata.minimum_history)

    def evaluate(self, symbol: str, bars: list[DailyBarSnapshot], parameters: dict) -> StrategySignal:
        short_window = max(int(parameters.get("short_window", 5)), 2)
        long_window = max(int(parameters.get("long_window", 20)), short_window + 1)
        base_position_pct = self._clamp_fraction(parameters.get("position_pct"), default=0.1)
        minimum_bars = max(long_window + 2, 22)

        if len(bars) < minimum_bars:
            return signal_from_payload(self._build_hold_signal(
                symbol,
                reason="insufficient_history",
                entry_price_ref=self._last_close(bars),
                market_regime="neutral",
            ))

        closes = [float(bar.close_price) for bar in bars]
        latest_close = closes[-1]
        previous_close = closes[-2]
        manager_gate = ManagerStyleGate(bars, parameters)

        short_now = self._average(closes[-short_window:])
        short_prev = self._average(closes[-short_window - 1:-1])
        long_now = self._average(closes[-long_window:])
        long_prev = self._average(closes[-long_window - 1:-1])

        spread_now = short_now - long_now
        spread_prev = short_prev - long_prev
        recent_high = max(closes[-6:-1]) if len(closes) >= 6 else latest_close
        recent_low = min(closes[-10:-1]) if len(closes) >= 10 else latest_close

        signal = "hold"
        strength = "weak"
        trigger_reason = "waiting_for_confirmation"
        position_pct = 0.0

        if spread_prev <= 0 < spread_now:
            signal = "buy"
            strength = "strong"
            trigger_reason = "golden_cross"
            position_pct = base_position_pct
        elif spread_prev >= 0 > spread_now:
            signal = "sell"
            strength = "strong"
            trigger_reason = "death_cross"
            position_pct = 1.0
        elif (
            spread_now > 0
            and spread_prev > 0
            and latest_close > short_now > long_now
            and latest_close >= recent_high
            and spread_now > spread_prev * 1.01
        ):
            signal = "buy"
            strength = "normal"
            trigger_reason = "trend_follow_buy"
            position_pct = min(base_position_pct, 0.12)
        elif (
            parameters.get("allow_backtest_trend_entry")
            and spread_now > 0
            and latest_close > short_now > long_now
            and len(bars) >= int(parameters.get("backtest_trend_entry_min_bars", 0) or 0)
        ):
            signal = "buy"
            strength = "weak"
            trigger_reason = "backtest_trend_entry"
            position_pct = min(base_position_pct, 0.12)
        elif (
            spread_now > 0
            and latest_close < short_now
            and (previous_close >= short_prev or latest_close <= recent_low * 1.02)
            and latest_close <= short_now * 0.998
        ):
            signal = "reduce"
            strength = "weak"
            trigger_reason = "trend_exit"
            position_pct = 0.5

        market_regime = self._market_regime(latest_close, short_now, long_now)
        stop_loss_price = round(max(long_now, latest_close * 0.95), 2) if signal in {"buy", "reduce"} else round(short_now, 2)
        take_profit_price = round(max(latest_close * 1.1, latest_close + (latest_close - stop_loss_price) * 2), 2)

        payload = {
            "symbol": symbol,
            "strategy": self.name,
            "signal": signal,
            "strength": strength,
            "trigger_reason": trigger_reason,
            "entry_price_ref": round(latest_close, 2),
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "position_pct": position_pct,
            "market_regime": market_regime,
            "requires_recommendation_confirmation": signal == "buy",
            "short_average": round(short_now, 4),
            "long_average": round(long_now, 4),
            "previous_short_average": round(short_prev, 4),
            "previous_long_average": round(long_prev, 4),
            "spread": round(spread_now, 4),
            "previous_spread": round(spread_prev, 4),
        }

        if signal == "buy":
            filter_result = manager_gate.evaluate_buy_filter(raw_trigger_reason=trigger_reason)
            if parameters.get("bypass_manager_buy_filter"):
                manager_gate.apply_to_signal(payload, filter_result)
            elif filter_result.filter_passed:
                manager_gate.apply_to_signal(payload, filter_result)
            else:
                manager_gate.suppress_buy_signal(payload, filter_result)
            return signal_from_payload(payload)

        manager_gate.apply_to_signal(payload, manager_gate.diagnostic_result())
        return signal_from_payload(payload)

    @staticmethod
    def _last_close(bars: list[DailyBarSnapshot]) -> float | None:
        return round(float(bars[-1].close_price), 2) if bars else None

    @staticmethod
    def _market_regime(latest_close: float, short_average: float, long_average: float) -> str:
        if latest_close > short_average > long_average:
            return "bullish"
        if latest_close < short_average < long_average:
            return "bearish"
        return "neutral"

    @staticmethod
    def _build_hold_signal(
        symbol: str,
        *,
        reason: str,
        entry_price_ref: float | None,
        market_regime: str,
    ) -> dict[str, object]:
        return {
            "symbol": symbol,
            "strategy": "moving_average",
            "signal": "hold",
            "strength": "weak",
            "trigger_reason": reason,
            "entry_price_ref": entry_price_ref,
            "stop_loss_price": None,
            "take_profit_price": None,
            "position_pct": 0.0,
            "market_regime": market_regime,
            "requires_recommendation_confirmation": False,
            "filter_passed": True,
            "filter_reasons": [],
            "trend_ok": None,
            "volume_ok": None,
            "volatility_ok": None,
            "stretch_ok": None,
            "market_regime_bias": None,
        }

    @staticmethod
    def _clamp_fraction(value: object, *, default: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(numeric, 1.0))

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values)
