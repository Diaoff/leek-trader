from pydantic import BaseModel


class SecuritySearchResult(BaseModel):
    symbol: str
    code: str
    name: str
    market: str
    pinyin_abbr: str
    tags: list[str]


class SecurityScreenResult(SecuritySearchResult):
    in_watchlist: bool = False
    market_cap: float | None = None
    price: float | None = None
    change_percent: float | None = None
