from app.trading.execution import ExecutionFill


class TradeMatcher:
    def match(self, symbol: str, quantity: int, price: float, *, side: str = "unknown") -> dict[str, object]:
        return ExecutionFill(
            symbol=symbol,
            side=side,
            requested_quantity=quantity,
            filled_quantity=quantity,
            unfilled_quantity=0,
            price=price,
        ).to_dict()
