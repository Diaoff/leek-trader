from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.market.quality_service import MarketDataQualityService
from app.market.providers.base import DailyBarSnapshot
from app.market.history_storage import MarketDailyBarStorage


client = TestClient(app)


def _bar(symbol: str, trade_date: date, *, trade_status: int | None = 1, is_st: bool | None = False, pe_ttm: float | None = 12.3):
    return DailyBarSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        open_price=10.0,
        close_price=10.5,
        high_price=10.8,
        low_price=9.9,
        volume=1000000.0,
        trade_status=trade_status,
        is_st=is_st,
        pe_ttm=pe_ttm,
    )


def test_market_data_quality_service_reports_gaps_and_flags(db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars([
        _bar("sh600000", date(2026, 4, 20), trade_status=0, is_st=False, pe_ttm=None),
        _bar("sh600000", date(2026, 4, 22), trade_status=1, is_st=True),
    ], source="baostock", adjustflag="2")

    report = MarketDataQualityService(db).build_daily_bar_quality_report(symbols=["600000.SH"])

    assert report.status == "ready"
    assert report.total_rows == 2
    assert report.symbols == ["sh600000"]
    assert report.symbol_reports[0].suspended_rows == 1
    assert report.symbol_reports[0].st_rows == 1
    assert report.symbol_reports[0].null_counts["pe_ttm"] == 1
    assert report.symbol_reports[0].calendar_gap_days == ["2026-04-21"]


def test_market_data_quality_api_returns_report(db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars([
        _bar("sh600000", date(2026, 4, 20), trade_status=0, is_st=False, pe_ttm=None),
        _bar("sh600000", date(2026, 4, 22), trade_status=1, is_st=True),
    ], source="baostock", adjustflag="2")

    response = client.post(
        "/api/v1/market/quality/daily-bars",
        json={"symbols": ["600000.SH"], "source": "baostock", "adjustflag": "2"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["total_rows"] == 2
    assert payload["symbol_reports"][0]["calendar_gap_days"] == ["2026-04-21"]
