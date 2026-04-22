from app.strategy.base import StrategyPlugin


class MovingAverageStrategy(StrategyPlugin):
    name = "moving_average"

    def evaluate(self, symbol: str, prices: list[float], parameters: dict) -> dict[str, object]:
        short_window = int(parameters.get("short_window", 5))
        long_window = int(parameters.get("long_window", 20))
        if len(prices) < long_window:
            signal = "hold"
        else:
            short_average = sum(prices[-short_window:]) / short_window
            long_average = sum(prices[-long_window:]) / long_window
            signal = "buy" if short_average > long_average else "sell"
        return {
            "symbol": symbol,
            "signal": signal,
            "strategy": self.name,
        }
