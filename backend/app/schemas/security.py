from pydantic import BaseModel


class SecuritySearchResult(BaseModel):
    symbol: str
    code: str
    name: str
    market: str
    pinyin_abbr: str
    tags: list[str]
