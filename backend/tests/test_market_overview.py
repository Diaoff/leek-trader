from datetime import UTC, datetime
from typing import Any

from app.market.overview_service import MarketOverviewCache, MarketOverviewService
from app.market.providers.base import (
    MarketBreadthBucketSnapshot,
    MarketBreadthDistributionSnapshot,
    MarketOverviewSnapshot,
    MarketSymbolSnapshot,
    MarketTurnoverSnapshot,
)
from app.market.providers.eastmoney_overview import EastMoneyOverviewProvider
from app.schemas.market import MarketOverviewRead


def build_market_symbol(
    *,
    symbol: str,
    name: str,
    price: float = 10.0,
    change_percent: float = 2.5,
    volume: float = 100000000.0,
    sector: str | None = None,
) -> MarketSymbolSnapshot:
    return MarketSymbolSnapshot(
        symbol=symbol,
        code=symbol[2:],
        name=name,
        price=price,
        change_percent=change_percent,
        volume=volume,
        sector=sector,
    )


def build_overview_snapshot(
    *,
    source: str = "stub",
    northbound_net_inflow: float | None = 123456789.0,
    hot_stocks: list[MarketSymbolSnapshot] | None = None,
) -> MarketOverviewSnapshot:
    hot_items = hot_stocks or [
        build_market_symbol(symbol="sz300750", name="宁德时代", change_percent=4.2, sector="锂电池"),
        build_market_symbol(symbol="sh600519", name="贵州茅台", change_percent=2.1, sector="白酒"),
    ]
    return MarketOverviewSnapshot(
        generated_at=datetime(2026, 4, 24, 10, 0, tzinfo=UTC),
        source=source,
        indices=[
            build_market_symbol(symbol="sh000001", name="上证指数", price=3301.23, change_percent=0.48),
            build_market_symbol(symbol="sz399001", name="深证成指", price=10432.10, change_percent=-0.22),
        ],
        top_gainers=[build_market_symbol(symbol="sz301667", name="纳百川", change_percent=12.1)],
        top_losers=[build_market_symbol(symbol="sh600898", name="ST美讯", change_percent=-10.0)],
        limit_up_total=12,
        limit_up_sample=[build_market_symbol(symbol="sz301667", name="纳百川", change_percent=12.1)],
        limit_down_total=3,
        limit_down_sample=[build_market_symbol(symbol="sh600898", name="ST美讯", change_percent=-10.0)],
        northbound_net_inflow=northbound_net_inflow,
        hot_stocks=hot_items,
        breadth_distribution=MarketBreadthDistributionSnapshot(
            advancing_count=2035,
            flat_count=109,
            declining_count=3352,
            buckets=[
                MarketBreadthBucketSnapshot(key="gt_10", label=">10%", count=48, tone="rise"),
                MarketBreadthBucketSnapshot(key="up_7_10", label="7~10%", count=72, tone="rise"),
                MarketBreadthBucketSnapshot(key="up_5_7", label="5~7%", count=84, tone="rise"),
                MarketBreadthBucketSnapshot(key="up_3_5", label="3~5%", count=221, tone="rise"),
                MarketBreadthBucketSnapshot(key="up_0_3", label="0~3%", count=1610, tone="rise"),
                MarketBreadthBucketSnapshot(key="down_0_3", label="0~-3%", count=2656, tone="fall"),
                MarketBreadthBucketSnapshot(key="down_3_5", label="-3~-5%", count=441, tone="fall"),
                MarketBreadthBucketSnapshot(key="down_5_7", label="-5~-7%", count=146, tone="fall"),
                MarketBreadthBucketSnapshot(key="down_7_10", label="-7~-10%", count=87, tone="fall"),
                MarketBreadthBucketSnapshot(key="lt_10", label="<-10%", count=22, tone="fall"),
            ],
            source=source,
        ),
        turnover=MarketTurnoverSnapshot(
            today_amount=265760000000.0,
            previous_day_amount=None,
            delta_amount=None,
            estimated_full_day_amount=265760000000.0,
            source=source,
        ),
    )


def build_overview_read() -> MarketOverviewRead:
    return MarketOverviewService._to_read_model(build_overview_snapshot())


def test_eastmoney_overview_provider_maps_payload(monkeypatch) -> None:
    ranked_rows: list[dict[str, Any]] = []
    change_values = [12.1, 9.9] + [4.2] * 98 + [0.0, -1.2, -10.0]
    volumes = [50000000.0, 30000000.0] + [1000000.0] * 98 + [2000000.0, 5000000.0, 1000000.0]

    for index, (change_percent, volume) in enumerate(zip(change_values, volumes), start=1):
        code = f"{index:06d}"
        ranked_rows.append(
            {
                "f12": code,
                "f14": f"个股{index}",
                "f2": 10.0 + index,
                "f3": change_percent,
                "f6": volume,
                "f13": 0 if index < 100000 else 1,
            }
        )

    ranked_rows[0]["f14"] = "纳百川"
    ranked_rows[-2]["f14"] = "平安银行"
    ranked_rows[-1]["f14"] = "ST美讯"

    def fake_get_json(url: str, *, params: dict[str, str]) -> dict[str, Any]:
        if url == EastMoneyOverviewProvider.index_endpoint:
            return {
                "data": {
                    "diff": [
                        {"f12": "000001", "f14": "上证指数", "f2": 3301.23, "f3": 0.48, "f6": 1234.0, "f13": 1},
                        {"f12": "399001", "f14": "深证成指", "f2": 10432.1, "f3": -0.22, "f6": 888.0, "f13": 0},
                    ]
                }
            }
        if url == EastMoneyOverviewProvider.northbound_endpoint:
            return {
                "data": {
                    "hk2sh": {"netBuyAmt": 1200000000.0},
                    "hk2sz": {"netBuyAmt": -200000000.0},
                }
            }

        fid = params["fid"]

        if fid == "f6":
            return {
                "data": {
                    "diff": [
                        {"f12": "300750", "f14": "宁德时代", "f2": 220.5, "f3": 4.2, "f6": 987654321.0, "f13": 0, "f100": "锂电池"},
                        {"f12": "600519", "f14": "贵州茅台", "f2": 1450.0, "f3": 2.1, "f6": 876543210.0, "f13": 1, "f100": "白酒"},
                    ]
                }
            }

        if fid == "f3":
            if params["po"] == "0" and params["pz"] == "8":
                return {
                    "data": {
                        "diff": [
                            {"f12": "000103", "f14": "ST美讯", "f2": 113.0, "f3": -10.0, "f6": 1000000.0, "f13": 0},
                            {"f12": "000102", "f14": "平安银行", "f2": 112.0, "f3": -1.2, "f6": 5000000.0, "f13": 0},
                        ]
                    }
                }
            page = int(params["pn"])
            page_size = int(params["pz"])
            start = (page - 1) * page_size
            end = start + page_size
            return {
                "data": {
                    "total": len(ranked_rows),
                    "diff": ranked_rows[start:end],
                }
            }

        return {"data": {"diff": []}}

    provider = EastMoneyOverviewProvider()
    monkeypatch.setattr(provider, "_get_json", fake_get_json)

    snapshot = provider.fetch_overview()

    assert snapshot.indices[0].name == "上证指数"
    assert snapshot.top_gainers[0].name == "纳百川"
    assert snapshot.limit_up_total == 2
    assert snapshot.limit_down_total == 1
    assert snapshot.top_losers[0].name == "ST美讯"
    assert snapshot.hot_stocks[0].sector == "锂电池"
    assert snapshot.northbound_net_inflow == 1000000000.0
    assert snapshot.breadth_distribution is None
    assert snapshot.turnover is None


def test_eastmoney_overview_provider_keeps_partial_rankings_when_later_pages_fail(monkeypatch) -> None:
    ranked_rows = [
        {
            "f12": f"{index:06d}",
            "f14": f"个股{index}",
            "f2": 10.0 + index,
            "f3": 6.0 - (index * 0.05),
            "f6": float(100000000 - (index * 1000)),
            "f13": 0,
            "f100": "测试板块",
        }
        for index in range(120)
    ]
    ranked_rows[0]["f14"] = "领涨股"
    ranked_rows[-1]["f14"] = "尾部股"
    ranked_rows[-1]["f3"] = -9.8

    descending_calls = 0

    def fake_get_json(url: str, *, params: dict[str, str]) -> dict[str, Any]:
        nonlocal descending_calls
        if url == EastMoneyOverviewProvider.index_endpoint:
            return {"data": {"diff": []}}
        if url == EastMoneyOverviewProvider.northbound_endpoint:
            return {"data": {}}

        fid = params["fid"]
        page = int(params["pn"])
        page_size = int(params["pz"])
        descending = params["po"] == "1"

        if fid == "f6":
            raise RuntimeError("hot ranking unavailable")

        if fid == "f3" and descending and page_size == 8:
            return {"data": {"diff": ranked_rows[:8]}}

        if fid == "f3" and not descending and page_size == 8:
            return {"data": {"diff": [{"f12": "009999", "f14": "跌幅股", "f2": 3.2, "f3": -9.8, "f6": 9999.0, "f13": 0}]}}

        if fid == "f3" and descending and page_size == provider.ranking_page_size:
            descending_calls += 1
            if page == 1:
                return {
                    "data": {
                        "total": len(ranked_rows),
                        "diff": ranked_rows[:provider.ranking_page_size],
                    }
                }
            raise RuntimeError(f"page {page} disconnected")

        return {"data": {"diff": []}}

    provider = EastMoneyOverviewProvider()
    monkeypatch.setattr(provider, "_get_json", fake_get_json)

    snapshot = provider.fetch_overview()

    assert descending_calls == 1
    assert snapshot.top_gainers[0].name == "领涨股"
    assert snapshot.top_losers[0].name == "跌幅股"
    assert snapshot.hot_stocks == []
    assert snapshot.breadth_distribution is None
    assert snapshot.limit_down_total == 0
    assert snapshot.turnover is None


def test_eastmoney_overview_provider_counts_board_specific_limit_moves(monkeypatch) -> None:
    ranked_rows = [
        {"f12": "300001", "f14": "创业样本", "f2": 21.0, "f3": 19.82, "f6": 1000000.0, "f13": 0, "f100": "成长"},
        {"f12": "600001", "f14": "主板样本", "f2": 11.0, "f3": 9.86, "f6": 1000000.0, "f13": 1, "f100": "主板"},
        {"f12": "430001", "f14": "北交样本", "f2": 31.0, "f3": 29.85, "f6": 1000000.0, "f13": 0, "f100": "北交所"},
        {"f12": "600898", "f14": "ST美讯", "f2": 4.8, "f3": -4.95, "f6": 1000000.0, "f13": 1, "f100": "ST"},
        {"f12": "688001", "f14": "科创样本", "f2": 18.0, "f3": -19.91, "f6": 1000000.0, "f13": 1, "f100": "科创"},
        {"f12": "830001", "f14": "北交跌停", "f2": 7.0, "f3": -29.88, "f6": 1000000.0, "f13": 0, "f100": "北交所"},
        {"f12": "000001", "f14": "普通波动", "f2": 10.0, "f3": -3.2, "f6": 1000000.0, "f13": 0, "f100": "主板"},
    ]

    def fake_get_json(url: str, *, params: dict[str, str]) -> dict[str, Any]:
        if url == EastMoneyOverviewProvider.index_endpoint:
            return {"data": {"diff": []}}
        if url == EastMoneyOverviewProvider.northbound_endpoint:
            return {"data": {}}

        fid = params["fid"]
        descending = params["po"] == "1"
        page_size = int(params["pz"])

        if fid == "f6":
            return {"data": {"diff": []}}
        if fid == "f3" and descending and page_size == 8:
            return {"data": {"diff": ranked_rows[:3]}}
        if fid == "f3" and not descending and page_size == 8:
            return {"data": {"diff": list(reversed(ranked_rows[-4:]))}}
        if fid == "f3" and descending and page_size == provider.ranking_page_size:
            return {"data": {"total": len(ranked_rows), "diff": ranked_rows}}
        if fid == "f3" and not descending and page_size == provider.ranking_page_size:
            return {"data": {"total": len(ranked_rows), "diff": sorted(ranked_rows, key=lambda item: item["f3"]) }}
        return {"data": {"diff": []}}

    provider = EastMoneyOverviewProvider()
    monkeypatch.setattr(provider, "_get_json", fake_get_json)

    snapshot = provider.fetch_overview()

    assert snapshot.limit_up_total == 3
    assert [item.name for item in snapshot.limit_up_sample] == ["创业样本", "主板样本", "北交样本"]
    assert snapshot.limit_down_total == 3
    assert [item.name for item in snapshot.limit_down_sample] == ["北交跌停", "科创样本", "ST美讯"]


def test_eastmoney_overview_provider_fetches_rankings_before_bulk_pagination(monkeypatch) -> None:
    events: list[str] = []

    def fake_get_json(url: str, *, params: dict[str, str]) -> dict[str, Any]:
        if url == EastMoneyOverviewProvider.index_endpoint:
            events.append("indices")
            return {"data": {"diff": []}}
        if url == EastMoneyOverviewProvider.northbound_endpoint:
            events.append("northbound")
            return {"data": {}}

        fid = params["fid"]
        page = params["pn"]
        descending = params["po"] == "1"

        if fid == "f3" and descending and page == "1" and params["pz"] == "8":
            events.append("top_gainers")
            return {"data": {"diff": [{"f12": "300001", "f14": "先拿榜单", "f2": 18.1, "f3": 9.9, "f6": 30000000.0, "f13": 0}]}}
        if fid == "f3" and not descending and page == "1" and params["pz"] == "8":
            events.append("top_losers")
            return {"data": {"diff": [{"f12": "300002", "f14": "先拿跌幅", "f2": 8.1, "f3": -9.1, "f6": 20000000.0, "f13": 0}]}}
        if fid == "f6":
            events.append("hot_stocks")
            return {"data": {"diff": [{"f12": "300003", "f14": "先拿热点", "f2": 28.1, "f3": 3.1, "f6": 90000000.0, "f13": 0, "f100": "AI"}]}}
        return {"data": {"diff": []}}

    provider = EastMoneyOverviewProvider()
    monkeypatch.setattr(provider, "_get_json", fake_get_json)

    snapshot = provider.fetch_overview()

    assert snapshot.top_gainers[0].name == "先拿榜单"
    assert snapshot.top_losers[0].name == "先拿跌幅"
    assert snapshot.hot_stocks[0].name == "先拿热点"
    assert events[:4] == ["indices", "top_gainers", "top_losers", "hot_stocks"]


def test_market_overview_service_degrades_when_all_providers_fail() -> None:
    class FailingProvider:
        name = "failing"

        def fetch_overview(self) -> MarketOverviewSnapshot:
            raise RuntimeError("upstream failed")

    service = MarketOverviewService(
        providers=[FailingProvider()],
        cache=MarketOverviewCache(ttl_seconds=60),
    )

    overview = service.get_overview(force_refresh=True)

    assert overview.indices == []
    assert overview.top_gainers == []
    assert overview.northbound.net_inflow is None
    assert overview.northbound.source == "none"
    assert overview.breadth_distribution is None
    assert overview.turnover_summary is None


def test_market_overview_service_preserves_cached_rankings_when_refresh_is_partial() -> None:
    cache = MarketOverviewCache(ttl_seconds=60)
    cache.set(
        build_overview_snapshot(
            source="cached",
            hot_stocks=[build_market_symbol(symbol="sz300750", name="缓存热点", change_percent=4.2, sector="锂电池")],
        )
    )

    class PartialProvider:
        name = "partial"

        def fetch_overview(self) -> MarketOverviewSnapshot:
            return MarketOverviewSnapshot(
                generated_at=datetime(2026, 4, 27, 13, 0, tzinfo=UTC),
                source="partial",
                indices=[build_market_symbol(symbol="sh000001", name="上证指数", price=3300.0, change_percent=0.2)],
                northbound_net_inflow=None,
            )

    service = MarketOverviewService(
        providers=[PartialProvider()],
        cache=cache,
    )

    overview = service.get_overview(force_refresh=True)

    assert overview.indices[0].name == "上证指数"
    assert overview.top_gainers[0].name == "纳百川"
    assert overview.top_losers[0].name == "ST美讯"
    assert overview.hot_stocks[0].name == "缓存热点"
    assert overview.breadth_distribution is not None
