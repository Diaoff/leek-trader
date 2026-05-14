from datetime import date, timedelta

from app.factors.service import FactorService
from app.market.providers.base import DailyBarSnapshot
from app.market.history_storage import MarketDailyBarStorage
from app.smart_selection.service import SmartSelectionService


def _bars(symbol: str, start: float) -> list[DailyBarSnapshot]:
    return [
        DailyBarSnapshot(
            symbol=symbol,
            trade_date=date(2026, 1, 1) + timedelta(days=index),
            open_price=start + index,
            close_price=start + index,
            high_price=start + index + 1,
            low_price=start + index - 1,
            volume=1000000,
        )
        for index in range(30)
    ]


def test_factor_service_ranks_symbols_with_indicator_values() -> None:
    result = FactorService().rank_symbols({"sh600519": _bars("sh600519", 10), "sz000001": _bars("sz000001", 20)}, factor="bbi")

    ranks = {item.symbol: item.rank for item in result}
    assert ranks["sz000001"] == 1
    assert ranks["sh600519"] == 2
    assert all(item.value is not None for item in result)
    assert all(item.computable is True for item in result)
    assert all(item.source_fields == ("close_price",) for item in result)


def test_factor_service_reports_insufficient_history() -> None:
    result = FactorService().rank_symbols({"sh600519": _bars("sh600519", 10)[:3]}, factor="cci")

    assert result[0].value is None
    assert result[0].rank is None
    assert result[0].missing_reason == "insufficient_history"
    assert result[0].computable is False
    assert result[0].missing_ratio == 1.0


def test_factor_service_reports_missing_fields() -> None:
    bars = _bars("sh600519", 10)
    bars[0].high_price = None  # type: ignore[assignment]

    result = FactorService().rank_symbols({"sh600519": bars}, factor="cci")

    assert result[0].missing_reason == "missing_fields"
    assert result[0].source_fields == ("close_price", "high_price", "low_price")
    assert result[0].computable is False


def test_smart_selection_service_rank_factors_uses_local_bars(db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars(_bars("sh600519", 10), source="baostock", adjustflag="2")
    storage.upsert_bars(_bars("sz000001", 20), source="baostock", adjustflag="2")

    ranked = SmartSelectionService().rank_factors(db, ["sh600519", "sz000001"], factor="bbi", limit=30)

    assert {item.symbol for item in ranked} == {"sh600519", "sz000001"}
    assert all(item.value is not None for item in ranked)
    assert all(item.computable is True for item in ranked)
