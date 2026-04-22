from pydantic import BaseModel


class StrategyRead(BaseModel):
    id: int
    tenant_id: str
    name: str
    strategy_type: str
    status: str
    parameters: dict
    latest_signal: str
    signal_symbol: str
