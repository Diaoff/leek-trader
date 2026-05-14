from datetime import UTC, datetime
from pathlib import Path
import runpy

import pytest

from app.market.provider_health import ProviderHealthTracker, provider_health_tracker
from app.market.source_health import MarketSourceHealthService
from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot
from app.market.data_service import MarketDataService
from app.market.service import QuoteService
from app.market.providers.base import QuoteSnapshot


class EmptyHistoryProvider:
    name = "empty-test"

    def fetch_daily_bars(self, symbol: str, limit: int = 60):
        return []


class FailingHistoryProvider:
    name = "fail-test"

    def fetch_daily_bars(self, symbol: str, limit: int = 60):
        raise RuntimeError("boom")


class QuoteProviderStub:
    name = "quote-test"

    def __init__(self, snapshots: list[QuoteSnapshot] | None = None, error: Exception | None = None) -> None:
        self.snapshots = snapshots or []
        self.error = error

    def fetch_quotes(self, symbols: list[str]):
        if self.error:
            raise self.error
        return self.snapshots


def _bar(symbol: str = "sh600000") -> DailyBarSnapshot:
    return DailyBarSnapshot(
        symbol=symbol,
        trade_date=datetime(2026, 4, 20, tzinfo=UTC).date(),
        open_price=10.0,
        close_price=10.5,
        high_price=10.8,
        low_price=9.9,
        volume=1000000.0,
    )


@pytest.fixture(autouse=True)
def reset_provider_health_tracker():
    provider_health_tracker.reset()
    yield
    provider_health_tracker.reset()


def test_provider_health_tracker_recovers_after_success() -> None:
    tracker = ProviderHealthTracker(failure_down_threshold=2)
    tracker.record(source="sina", operation="daily_bar", status="failure", recorded_at=datetime(2026, 1, 1, tzinfo=UTC))
    tracker.record(source="sina", operation="daily_bar", status="failure", recorded_at=datetime(2026, 1, 2, tzinfo=UTC))

    assert tracker.summary("sina").runtime_health_level == "down"

    tracker.record(source="sina", operation="daily_bar", status="success", row_count=3, latency_ms=10.0, recorded_at=datetime(2026, 1, 3, tzinfo=UTC))
    summary = tracker.summary("sina")

    assert summary.runtime_health_level == "degraded"
    assert summary.last_success_at == "2026-01-03T00:00:00+00:00"
    assert summary.recent_failure_count == 2
    assert summary.avg_latency_ms == 10.0


def test_source_health_includes_runtime_provider_fields(db) -> None:
    storage = MarketDailyBarStorage(db)
    storage.upsert_bars([_bar()], source="baostock", adjustflag="2")
    provider_health_tracker.record(source="baostock", operation="daily_bar", status="failure")

    report = MarketSourceHealthService(db).build_daily_bar_source_health(symbols=["sh600000"], sources=["baostock"])
    item = report.sources[0]

    assert item.runtime_health_level == "degraded"
    assert item.health_level == "degraded"
    assert item.recent_failure_count == 1
    assert item.last_failure_at is not None


def test_market_data_service_records_empty_and_failure_provider_events() -> None:
    service = MarketDataService(history_providers=[EmptyHistoryProvider(), FailingHistoryProvider()])

    payload = service.get_daily_bars_with_source("sh600000", force_refresh=True)

    assert payload.bars == []
    assert provider_health_tracker.summary("empty-test").recent_empty_count == 1
    assert provider_health_tracker.summary("fail-test").recent_failure_count == 1


def test_quote_service_records_provider_events() -> None:
    service = QuoteService(providers=[QuoteProviderStub(error=RuntimeError("quote failed"))])

    assert service.list_quotes(["sh600000"], force_refresh=True) == []
    assert provider_health_tracker.summary("quote-test").recent_failure_count == 1


def test_optional_data_provider_spike_skips_missing_dependencies() -> None:
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "spike_data_providers.py"))
    result = namespace["run_spike"]()

    assert result["status"] == "ready"
    assert {item["package"] for item in result["providers"]} == {"adata", "efinance"}
    assert all("failure_modes" in item for item in result["providers"])
    assert all("decision" in item for item in result["providers"])
    assert all("integration_scope" in item for item in result["providers"])
    assert all("license_status" in item for item in result["providers"])
    assert all("dependency_status" in item for item in result["providers"])
    assert all("fallback_plan" in item for item in result["providers"])
    decisions = {item["package"]: item["decision"] for item in result["providers"]}
    assert decisions == {"adata": "adopted_for_research", "efinance": "deferred"}
