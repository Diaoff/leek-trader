from app.strategy.base import StrategyPlugin


class MacdStrategy(StrategyPlugin):
    name = "macd"

    def evaluate(self, symbol: str, prices: list[float], parameters: dict) -> dict[str, object]:
        fast_period = int(parameters.get("fast_period", 12))
        slow_period = int(parameters.get("slow_period", 26))
        if len(prices) < slow_period:
            signal = "hold"
        else:
            fast_average = sum(prices[-fast_period:]) / fast_period
            slow_average = sum(prices[-slow_period:]) / slow_period
            signal = "buy" if fast_average > slow_average else "sell"
        return {
            "symbol": symbol,
            "signal": signal,
            "strategy": self.name,
        }
