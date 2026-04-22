class TradeMatcher:
    def match(self, symbol: str, quantity: int, price: float) -> dict[str, object]:
        return {
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "matched": True,
            "mode": "paper",
        }
