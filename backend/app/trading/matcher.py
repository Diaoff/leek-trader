from app.trading.execution import ExecutionFill, ExecutionOrderIntent


class TradeMatcher:
    def match(self, symbol: str, quantity: int, price: float, *, side: str = "unknown") -> dict[str, object]:
        return ExecutionFill.from_intent(
            ExecutionOrderIntent(
                symbol=symbol,
                side=side,
                requested_quantity=quantity,
                price_reference=price,
                mode="paper",
            ),
            filled_quantity=quantity,
            price=price,
        ).to_dict()
