from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ExecutionFill:
    symbol: str
    side: str
    requested_quantity: int
    filled_quantity: int
    unfilled_quantity: int
    price: float
    fee: float = 0.0
    matched: bool = True
    mode: str = "paper"
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
