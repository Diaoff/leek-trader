from __future__ import annotations

from functools import lru_cache

from app.market.security_catalog import find_security_by_symbol


@lru_cache(maxsize=4096)
def security_name(symbol: str) -> str | None:
    security = find_security_by_symbol(symbol)
    if security is None:
        return None
    name = str(security.get("name") or "").strip()
    return name or None


def security_display(symbol: str) -> str:
    name = security_name(symbol)
    return f"{name} · {symbol}" if name else symbol
