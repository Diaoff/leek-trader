import json
import logging
from functools import lru_cache
from pathlib import Path

import httpx

CATALOG_PATH = Path(__file__).resolve().parent / "data" / "a_share_securities.json"
TENCENT_SEARCH_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/smartbox/search/get"
SUPPORTED_MARKETS = {
    "sh": "沪A",
    "sz": "深A",
    "bj": "北交所",
}

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_security_catalog() -> list[dict[str, object]]:
    with CATALOG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def find_security_by_symbol(symbol: str) -> dict[str, object] | None:
    normalized = symbol.strip().lower()
    local = _find_local_security_by_symbol(normalized)
    if local is not None:
        return local
    return _fetch_remote_security_by_symbol(normalized)


def search_securities(query: str, limit: int = 20) -> list[dict[str, object]]:
    normalized = query.strip().lower()
    if not normalized:
        return []

    try:
        remote_results = _search_remote_securities(normalized, limit)
    except Exception as error:
        logger.warning("Tencent security search failed for query=%s: %s", normalized, error)
    else:
        if remote_results:
            return remote_results[:limit]

    return _search_local_securities(normalized, limit)


def _find_local_security_by_symbol(symbol: str) -> dict[str, object] | None:
    for entry in load_security_catalog():
        if str(entry["symbol"]).lower() == symbol:
            return entry
    return None


@lru_cache(maxsize=512)
def _fetch_remote_security_by_symbol(symbol: str) -> dict[str, object] | None:
    market = symbol[:2]
    code = symbol[2:]
    if market not in SUPPORTED_MARKETS or not code:
        return None

    try:
        results = _search_remote_securities(code, limit=30)
    except Exception as error:
        logger.warning("Tencent security lookup failed for symbol=%s: %s", symbol, error)
        return None

    return next((entry for entry in results if str(entry["symbol"]).lower() == symbol), None)


def _search_remote_securities(query: str, limit: int) -> list[dict[str, object]]:
    with httpx.Client(timeout=5.0) as client:
        response = client.get(TENCENT_SEARCH_URL, params={"q": query})
        response.raise_for_status()

    payload = response.json()
    stock_rows = payload.get("data", {}).get("stock", []) or []
    results: list[tuple[int, dict[str, object]]] = []
    seen_symbols: set[str] = set()
    normalized_query = query.strip().lower()

    for row in stock_rows:
        if not isinstance(row, list) or len(row) < 4:
            continue

        market = str(row[0]).strip().lower()
        code = str(row[1]).strip()
        name = str(row[2]).strip()
        pinyin_abbr = str(row[3]).strip().lower()
        symbol = _normalize_remote_symbol(market, code)

        if market not in SUPPORTED_MARKETS or symbol is None or symbol in seen_symbols:
            continue

        entry = {
            "symbol": symbol,
            "code": code,
            "name": name or symbol,
            "market": SUPPORTED_MARKETS[market],
            "pinyin_abbr": pinyin_abbr,
            "tags": _infer_tags(symbol, name),
        }
        score = _score_entry(entry, normalized_query)
        if score <= 0:
            continue
        seen_symbols.add(symbol)
        results.append((score, entry))

    results.sort(key=lambda item: (-item[0], str(item[1]["code"])))
    return [entry for _, entry in results[:limit]]


def _search_local_securities(query: str, limit: int) -> list[dict[str, object]]:
    results: list[tuple[int, dict[str, object]]] = []
    for entry in load_security_catalog():
        score = _score_entry(entry, query)
        if score > 0:
            results.append((score, entry))

    results.sort(key=lambda item: (-item[0], str(item[1]["code"])))
    return [entry for _, entry in results[:limit]]


def _score_entry(entry: dict[str, object], query: str) -> int:
    code = str(entry["code"]).lower()
    symbol = str(entry["symbol"]).lower()
    name = str(entry["name"]).lower()
    pinyin_abbr = str(entry.get("pinyin_abbr", "")).lower()

    if code == query:
        return 120
    if symbol == query:
        return 115
    if code.startswith(query):
        return 100
    if symbol.startswith(query):
        return 95
    if pinyin_abbr.startswith(query):
        return 90
    if query in name:
        return 80
    if query in pinyin_abbr:
        return 70
    return 0


def _normalize_remote_symbol(market: str, code: str) -> str | None:
    normalized_market = market.lower()
    normalized_code = code.lower()
    if normalized_market not in SUPPORTED_MARKETS:
        return None
    return f"{normalized_market}{normalized_code}"


def _infer_tags(symbol: str, name: str) -> list[str]:
    tags: list[str] = []
    if symbol.startswith("sz300"):
        tags.append("创")
    if "st" in name.lower():
        tags.append("ST")
    return tags
