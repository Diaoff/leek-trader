from datetime import date

import pytest
from sqlalchemy import select

from app.market.baostock_sync_service import BaoStockHistorySyncService
from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot
from app.market.providers.baostock import BaoStockDailyBarProvider, BaoStockLoginError
from app.market.rl_dataset_service import RL_DATASET_FIELDS, RLDatasetBuilder
from app.models.market_daily_bar import MarketDailyBar
from app.tasks.market_tasks import sync_baostock_history_task


def _bar(symbol: str, trade_date: date, *, trade_status: int | None = 1, is_st: bool | None = False, close_price: float = 10.5) -> DailyBarSnapshot:
    return DailyBarSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        open_price=10.0,
        close_price=close_price,
        high_price=10.8,
        low_price=9.9,
        volume=1000000.0,
        turnover=12000000.0,
        change_pct=1.5,
        turnover_rate=2.3,
        preclose=10.2,
        trade_status=trade_status,
        pe_ttm=12.1,
        pb_mrq=1.2,
        ps_ttm=2.1,
        pcf_ncf_ttm=3.1,
        is_st=is_st,
    )


class StubBaoStockProvider:
    name = "baostock"

    def __init__(self, bars_by_symbol: dict[str, list[DailyBarSnapshot]] | None = None, failures: set[str] | None = None) -> None:
        self.adjustflag = "2"
        self.calls: list[tuple[str, date, date]] = []
        self.bars_by_symbol = bars_by_symbol or {}
        self.failures = failures or set()

    def fetch_daily_bars_range(self, symbol: str, *, start_date: date, end_date: date) -> list[DailyBarSnapshot]:
        self.calls.append((symbol, start_date, end_date))
        if symbol in self.failures:
            raise RuntimeError("provider boom")
        return self.bars_by_symbol.get(symbol, [_bar(symbol, start_date)])


def test_baostock_provider_parses_rl_extension_fields_and_symbol_forms() -> None:
    rows = [
        {
            "date": "2026-04-21",
            "open": "10.00",
            "high": "10.80",
            "low": "9.90",
            "close": "10.50",
            "preclose": "10.20",
            "volume": "1000000",
            "amount": "12000000",
            "turn": "2.3",
            "tradestatus": "1",
            "pctChg": "1.5",
            "peTTM": "12.1",
            "pbMRQ": "1.2",
            "psTTM": "2.1",
            "pcfNcfTTM": "3.1",
            "isST": "1",
        }
    ]

    bars = BaoStockDailyBarProvider.parse_daily_bars("600000.SH", rows)

    assert BaoStockDailyBarProvider.to_baostock_symbol("sh.600000") == "sh.600000"
    assert BaoStockDailyBarProvider.to_baostock_symbol("600000.SH") == "sh.600000"
    assert BaoStockDailyBarProvider.to_baostock_symbol("sz000001") == "sz.000001"
    assert BaoStockDailyBarProvider.to_baostock_symbol("000001.SZ") == "sz.000001"
    assert bars[0].symbol == "sh600000"
    assert bars[0].preclose == 10.2
    assert bars[0].trade_status == 1
    assert bars[0].pe_ttm == 12.1
    assert bars[0].pb_mrq == 1.2
    assert bars[0].ps_ttm == 2.1
    assert bars[0].pcf_ncf_ttm == 3.1
    assert bars[0].is_st is True


def test_market_daily_bar_storage_upserts_without_duplicates(db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars([_bar("600000.SH", date(2026, 4, 21), close_price=10.5)], source="baostock", adjustflag="2")
    storage.upsert_bars([_bar("sh600000", date(2026, 4, 21), close_price=11.5)], source="baostock", adjustflag="2")

    rows = db.scalars(select(MarketDailyBar)).all()
    result = storage.list_bars(symbol="sh.600000", source="baostock", adjustflag="2")

    assert len(rows) == 1
    assert result.bars[0].symbol == "sh600000"
    assert result.bars[0].close_price == 11.5


def test_market_daily_bar_storage_dedupes_same_batch_symbol_trade_date(db) -> None:
    storage = MarketDailyBarStorage(db)

    changed = storage.upsert_bars(
        [
            _bar("600000.SH", date(2026, 4, 21), close_price=10.5),
            _bar("sh600000", date(2026, 4, 21), close_price=11.5),
        ],
        source="baostock",
        adjustflag="2",
    )

    rows = db.scalars(select(MarketDailyBar)).all()
    result = storage.list_bars(symbol="sh600000", source="baostock", adjustflag="2")
    assert changed == 1
    assert len(rows) == 1
    assert result.bars[0].close_price == 10.5


class CountingBaoStockModule:
    def __init__(self) -> None:
        self.login_count = 0
        self.logout_count = 0
        self.query_codes: list[str] = []

    def login(self):
        self.login_count += 1
        return type("LoginResult", (), {"error_code": "0", "error_msg": ""})()

    def logout(self):
        self.logout_count += 1

    def query_history_k_data_plus(self, code, fields, start_date, end_date, frequency, adjustflag):
        self.query_codes.append(code)
        return type(
            "QueryResult",
            (),
            {
                "error_code": "0",
                "error_msg": "",
                "get_data": lambda self: [
                    {
                        "date": start_date,
                        "open": "10.0",
                        "high": "10.8",
                        "low": "9.9",
                        "close": "10.5",
                        "volume": "1000000",
                        "amount": "12000000",
                        "turn": "2.3",
                        "tradestatus": "1",
                        "pctChg": "1.5",
                        "peTTM": "12.1",
                        "pbMRQ": "1.2",
                        "psTTM": "2.1",
                        "pcfNcfTTM": "3.1",
                        "isST": "0",
                    }
                ],
            },
        )()


def test_baostock_sync_reuses_single_login_for_batch(db) -> None:
    baostock_module = CountingBaoStockModule()
    provider = BaoStockDailyBarProvider(baostock_module=baostock_module)

    result = BaoStockHistorySyncService(db, provider=provider).sync_history(
        symbols=["600000.SH", "000001.SZ"],
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 21),
        adjustflag="2",
    )

    assert result.status == "completed"
    assert result.success_count == 2
    assert baostock_module.login_count == 1
    assert baostock_module.logout_count == 1
    assert baostock_module.query_codes == ["sh.600000", "sz.000001"]


def test_baostock_sync_collects_successes_and_failures(db) -> None:
    provider = StubBaoStockProvider(failures={"sz000001"})
    result = BaoStockHistorySyncService(db, provider=provider).sync_history(
        symbols=["600000.SH", "000001.SZ"],
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 21),
        adjustflag="2",
    )

    assert result.status == "partial_success"
    assert result.success_count == 1
    assert result.failure_count == 1
    assert result.failures[0].symbol == "sz000001"
    assert result.bars_upserted == 1


def test_baostock_sync_stops_batch_after_login_failure(db) -> None:
    provider = StubBaoStockProvider(failures={"sh600000"})

    def fail_login(symbol: str, *, start_date: date, end_date: date) -> list[DailyBarSnapshot]:
        provider.calls.append((symbol, start_date, end_date))
        raise BaoStockLoginError("baostock login failed: 网络接收错误。")

    provider.fetch_daily_bars_range = fail_login

    result = BaoStockHistorySyncService(db, provider=provider).sync_history(
        symbols=["600000.SH", "000001.SZ", "300750.SZ"],
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 21),
        adjustflag="2",
    )

    assert result.status == "failed"
    assert provider.calls == [("sh600000", date(2026, 4, 20), date(2026, 4, 21))]
    assert [failure.symbol for failure in result.failures] == ["sh600000", "sz000001", "sz300750"]
    assert result.failures[1].reason.startswith("skipped after BaoStock login failure")


def test_baostock_sync_reports_per_symbol_progress_and_persists_each_symbol(db) -> None:
    provider = StubBaoStockProvider(
        bars_by_symbol={
            "sh600000": [_bar("sh600000", date(2026, 4, 20))],
            "sz000001": [_bar("sz000001", date(2026, 4, 21))],
        }
    )
    progress_events: list[tuple[int, int, str, list[str], int]] = []

    def progress(step: int, total: int, label: str, details: list[str]) -> None:
        persisted_rows = len(db.scalars(select(MarketDailyBar)).all())
        progress_events.append((step, total, label, details, persisted_rows))

    result = BaoStockHistorySyncService(db, provider=provider).sync_history(
        symbols=["600000.SH", "000001.SZ"],
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 21),
        adjustflag="2",
        progress_callback=progress,
    )

    labels = [event[2] for event in progress_events]
    saved_events = [event for event in progress_events if event[2].startswith("已保存")]
    assert result.status == "completed"
    assert labels == ["正在获取 sh600000 日线", "已保存 sh600000 日线", "正在获取 sz000001 日线", "已保存 sz000001 日线"]
    assert saved_events[0][4] == 1
    assert saved_events[1][4] == 2
    assert result.bars_upserted == 2


def test_baostock_incremental_sync_starts_after_latest_trade_date(db) -> None:
    MarketDailyBarStorage(db).upsert_bars([_bar("sh600000", date(2026, 4, 21))], source="baostock", adjustflag="2")
    provider = StubBaoStockProvider(bars_by_symbol={"sh600000": [_bar("sh600000", date(2026, 4, 22))]})

    result = BaoStockHistorySyncService(db, provider=provider).sync_history(
        symbols=["600000.SH"],
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 23),
        adjustflag="2",
        incremental=True,
    )

    assert provider.calls == [("sh600000", date(2026, 4, 22), date(2026, 4, 23))]
    assert result.incremental is True
    assert result.resolved_ranges[0].start_date == "2026-04-22"
    assert result.resolved_ranges[0].skipped is False
    assert result.bars_upserted == 1


def test_baostock_incremental_sync_skips_symbols_already_up_to_date(db) -> None:
    MarketDailyBarStorage(db).upsert_bars([_bar("sh600000", date(2026, 4, 23))], source="baostock", adjustflag="2")
    provider = StubBaoStockProvider()

    result = BaoStockHistorySyncService(db, provider=provider).sync_history(
        symbols=["600000.SH"],
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 23),
        adjustflag="2",
        incremental=True,
    )

    assert provider.calls == []
    assert result.status == "completed"
    assert result.success_count == 1
    assert result.bars_upserted == 0
    assert result.resolved_ranges[0].skipped is True
    assert result.resolved_ranges[0].reason == "already_up_to_date"


def test_baostock_sync_requires_explicit_symbols(db) -> None:
    with pytest.raises(ValueError, match="symbols"):
        BaoStockHistorySyncService(db, provider=StubBaoStockProvider()).sync_history(
            symbols=[],
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 21),
        )


def test_rl_dataset_filters_suspended_days_and_preserves_st_flag(db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars(
        [
            _bar("sh600000", date(2026, 4, 21), trade_status=0, is_st=False),
            _bar("sh600000", date(2026, 4, 22), trade_status=1, is_st=True),
        ],
        source="baostock",
        adjustflag="2",
    )

    dataset = RLDatasetBuilder(db).build_dataset(symbols=["600000.SH"])

    assert dataset.status == "ready"
    assert dataset.fields == RL_DATASET_FIELDS
    assert dataset.count == 1
    assert dataset.records[0]["trade_date"] == "2026-04-22"
    assert dataset.records[0]["is_st"] is True


def test_rl_dataset_split_uses_split_date_and_gap_days(db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars(
        [
            _bar("sh600000", date(2026, 4, 20)),
            _bar("sh600000", date(2026, 4, 21)),
            _bar("sh600000", date(2026, 4, 22)),
            _bar("sh600000", date(2026, 4, 23)),
        ],
        source="baostock",
        adjustflag="2",
    )

    result = RLDatasetBuilder(db).build_split_dataset(symbols=["600000.SH"], split_date=date(2026, 4, 23), gap_days=1)

    assert result.schema_version == "rl-daily-bars/v1"
    assert [record["trade_date"] for record in result.train.records] == ["2026-04-20", "2026-04-21"]
    assert [record["trade_date"] for record in result.test.records] == ["2026-04-23"]
    assert "price" in result.feature_groups


def test_rl_dataset_quality_reports_nulls_suspensions_st_and_calendar_gaps(db) -> None:
    storage = MarketDailyBarStorage(db)
    first = _bar("sh600000", date(2026, 4, 20), trade_status=0, is_st=False)
    first.pe_ttm = None
    second = _bar("sh600000", date(2026, 4, 22), trade_status=1, is_st=True)
    storage.upsert_bars([first, second], source="baostock", adjustflag="2")

    result = RLDatasetBuilder(db).build_quality_report(symbols=["600000.SH"])
    report = result.symbol_reports[0]

    assert result.status == "ready"
    assert result.total_rows == 2
    assert report.suspended_rows == 1
    assert report.st_rows == 1
    assert report.null_counts["pe_ttm"] == 1
    assert report.calendar_gap_days == ["2026-04-21"]


def test_sync_baostock_history_task_rejects_empty_symbols(client) -> None:
    with pytest.raises(ValueError, match="symbols"):
        sync_baostock_history_task([], "2026-04-20", "2026-04-21")
