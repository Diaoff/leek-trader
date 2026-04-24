from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import app.api.market as market_api_module
import app.market.research_service as research_module
from app.market.overview_service import MarketOverviewCache, MarketOverviewService
from app.market.providers.base import (
    DailyBarSnapshot,
    MarketBreadthBucketSnapshot,
    MarketBreadthDistributionSnapshot,
    MarketOverviewSnapshot,
    MarketSymbolSnapshot,
    MarketTurnoverSnapshot,
)
from app.market.providers.eastmoney_overview import EastMoneyOverviewProvider
from app.market.research_service import MarketResearchService
from app.models.recommendation_item import RecommendationItem
from app.models.recommendation_run import RecommendationRun, RecommendationRunStatus
from app.schemas.market import MarketLimitStatsRead, MarketOverviewRead, MarketQuoteRead, NorthboundSummaryRead


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


def build_bar(symbol: str, trade_date: date, open_price: float, close_price: float, high_price: float, low_price: float) -> DailyBarSnapshot:
    return DailyBarSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        open_price=open_price,
        close_price=close_price,
        high_price=high_price,
        low_price=low_price,
        volume=1000000.0,
        turnover=2000000.0,
        amplitude_pct=3.0,
        change_pct=((close_price / open_price) - 1) * 100 if open_price else 0.0,
        turnover_rate=1.5,
    )


def build_research_bars(symbol: str, closes: list[float]) -> list[DailyBarSnapshot]:
    bars: list[DailyBarSnapshot] = []
    for index, close in enumerate(closes, start=1):
        bars.append(
            build_bar(
                symbol,
                date(2026, 3, 1).replace(day=min(index, 28)),
                close - 0.5,
                close,
                close + 1.0,
                close - 1.0,
            )
        )
    return bars


def test_eastmoney_overview_provider_maps_payload(monkeypatch) -> None:
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
        limit = int(params["pz"])
        descending = params["po"] == "1"

        if fid == "f6":
            return {
                "data": {
                    "diff": [
                        {"f12": "300750", "f14": "宁德时代", "f2": 220.5, "f3": 4.2, "f6": 987654321.0, "f13": 0, "f100": "锂电池"},
                        {"f12": "600519", "f14": "贵州茅台", "f2": 1450.0, "f3": 2.1, "f6": 876543210.0, "f13": 1, "f100": "白酒"},
                    ]
                }
            }

        if fid == "f3" and limit == 8 and descending:
            return {
                "data": {
                    "diff": [
                        {"f12": "301667", "f14": "纳百川", "f2": 25.2, "f3": 12.1, "f6": 50000000.0, "f13": 0},
                        {"f12": "300750", "f14": "宁德时代", "f2": 220.5, "f3": 4.2, "f6": 987654321.0, "f13": 0},
                    ]
                }
            }

        if fid == "f3" and limit == 8 and not descending:
            return {
                "data": {
                    "diff": [
                        {"f12": "600898", "f14": "ST美讯", "f2": 1.9, "f3": -10.0, "f6": 1000000.0, "f13": 1},
                        {"f12": "000001", "f14": "平安银行", "f2": 10.1, "f3": -1.2, "f6": 5000000.0, "f13": 0},
                    ]
                }
            }

        if fid == "f3" and limit == 200 and descending:
            return {
                "data": {
                    "diff": [
                        {"f12": "301667", "f14": "纳百川", "f2": 25.2, "f3": 12.1, "f6": 50000000.0, "f13": 0},
                        {"f12": "300001", "f14": "特锐德", "f2": 18.1, "f3": 9.9, "f6": 30000000.0, "f13": 0},
                        {"f12": "300750", "f14": "宁德时代", "f2": 220.5, "f3": 4.2, "f6": 987654321.0, "f13": 0},
                    ]
                }
            }

        return {
            "data": {
                "diff": [
                    {"f12": "600898", "f14": "ST美讯", "f2": 1.9, "f3": -10.0, "f6": 1000000.0, "f13": 1},
                    {"f12": "002001", "f14": "新和成", "f2": 19.9, "f3": -9.8, "f6": 3000000.0, "f13": 0},
                    {"f12": "000001", "f14": "平安银行", "f2": 10.1, "f3": -1.2, "f6": 5000000.0, "f13": 0},
                ]
            }
        }

    provider = EastMoneyOverviewProvider()
    monkeypatch.setattr(provider, "_get_json", fake_get_json)

    snapshot = provider.fetch_overview()

    assert snapshot.indices[0].name == "上证指数"
    assert snapshot.top_gainers[0].name == "纳百川"
    assert snapshot.limit_up_total == 2
    assert snapshot.limit_down_total == 2
    assert snapshot.hot_stocks[0].sector == "锂电池"
    assert snapshot.northbound_net_inflow == 1000000000.0
    assert snapshot.breadth_distribution is not None
    assert snapshot.breadth_distribution.advancing_count == 0
    assert snapshot.breadth_distribution.declining_count == 3
    assert snapshot.turnover is not None
    assert snapshot.turnover.today_amount == 9000000.0


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


def test_market_research_service_persists_snapshot_and_previous_history(db, monkeypatch) -> None:
    test_pool = [
        {"symbol": "sh600519", "code": "600519", "name": "贵州茅台", "sector": "白酒"},
        {"symbol": "sz300750", "code": "300750", "name": "宁德时代", "sector": "锂电池"},
        {"symbol": "sh601012", "code": "601012", "name": "隆基绿能", "sector": "光伏"},
        {"symbol": "sz300308", "code": "300308", "name": "中际旭创", "sector": "算力硬件"},
        {"symbol": "sh600036", "code": "600036", "name": "招商银行", "sector": "银行"},
        {"symbol": "sz000333", "code": "000333", "name": "美的集团", "sector": "家电"},
    ]
    monkeypatch.setattr(research_module, "DEFAULT_RESEARCH_POOL", test_pool)

    class StubOverviewService:
        def get_overview(self, *, force_refresh: bool = False) -> MarketOverviewRead:
            return MarketOverviewRead(
                generated_at="2026-04-24T10:00:00+00:00",
                indices=[],
                top_gainers=[],
                top_losers=[],
                limit_up=MarketLimitStatsRead(total=9, sample=[], source="stub"),
                limit_down=MarketLimitStatsRead(total=2, sample=[], source="stub"),
                northbound=NorthboundSummaryRead(net_inflow=180000000.0, unit="CNY", source="stub"),
                hot_stocks=[],
            )

    quotes = {
        "sh600519": MarketQuoteRead(symbol="sh600519", code="600519", name="贵州茅台", price=1450.0, change_percent=-1.8, volume=1000.0),
        "sz300750": MarketQuoteRead(symbol="sz300750", code="300750", name="宁德时代", price=210.0, change_percent=0.5, volume=1000.0),
        "sh601012": MarketQuoteRead(symbol="sh601012", code="601012", name="隆基绿能", price=18.5, change_percent=1.2, volume=1000.0),
        "sz300308": MarketQuoteRead(symbol="sz300308", code="300308", name="中际旭创", price=160.0, change_percent=-0.8, volume=1000.0),
        "sh600036": MarketQuoteRead(symbol="sh600036", code="600036", name="招商银行", price=35.0, change_percent=0.2, volume=1000.0),
        "sz000333": MarketQuoteRead(symbol="sz000333", code="000333", name="美的集团", price=70.0, change_percent=0.1, volume=1000.0),
    }
    histories = {
        "sh600519": build_research_bars("sh600519", [1650, 1600, 1550, 1500, 1475, 1450]),
        "sz300750": build_research_bars("sz300750", [180, 185, 190, 198, 205, 210]),
        "sh601012": build_research_bars("sh601012", [15.5, 16.2, 16.8, 17.2, 17.9, 18.5]),
        "sz300308": build_research_bars("sz300308", [170, 176, 182, 178, 170, 160]),
        "sh600036": build_research_bars("sh600036", [32.0, 32.8, 33.6, 34.1, 34.7, 35.0]),
        "sz000333": build_research_bars("sz000333", [66.5, 67.0, 67.8, 68.5, 69.2, 70.0]),
    }

    class StubQuoteService:
        def list_quotes(self, symbols: list[str], *, force_refresh: bool = False) -> list[MarketQuoteRead]:
            return [quotes[symbol] for symbol in symbols if symbol in quotes]

    class StubHistoryService:
        def get_daily_bars_map(self, symbols: list[str], limit: int = 60) -> dict[str, list[DailyBarSnapshot]]:
            return {symbol: histories.get(symbol, []) for symbol in symbols}

    service = MarketResearchService(
        overview_service=StubOverviewService(),
        quote_service=StubQuoteService(),
        history_service=StubHistoryService(),
    )

    first_run = service.execute_run(db, triggered_by="manual")
    second_run = service.execute_run(db, triggered_by="manual")

    assert first_run.status == RecommendationRunStatus.SUCCEEDED
    assert first_run.recommendation_count >= 5
    assert second_run.recommendation_count >= 5

    items = db.query(RecommendationItem).filter(RecommendationItem.run_id == second_run.id).all()
    assert len(items) >= 5
    assert any(item.layer in {"oversold", "support", "pullback"} for item in items)
    assert any(item.previous_recommendation_price is not None for item in items)

    previous_item = service.get_previous_recommendation(db, "sh600519", before_run_id=second_run.id)
    assert previous_item is not None
    assert previous_item.run_id == first_run.id


def test_market_overview_and_research_api_return_snapshot_data(client, db, monkeypatch) -> None:
    run = RecommendationRun(
        status=RecommendationRunStatus.SUCCEEDED,
        triggered_by="manual",
        candidate_pool_size=12,
        recommendation_count=1,
        northbound_net_inflow=123456789.0,
        market_sentiment={
            "label": "strong",
            "title": "情绪偏强",
            "score": 68.0,
            "selection_mode": "momentum",
            "advancing_count": 18,
            "declining_count": 6,
            "flat_count": 2,
            "limit_up_count": 10,
            "limit_down_count": 1,
            "northbound_net_inflow": 123456789.0,
            "summary": "上涨家数占优。",
        },
        sector_momentum_top=[
            {
                "sector": "锂电池",
                "rank": 1,
                "avg_change_pct": 3.4,
                "positive_ratio": 0.8,
                "candidate_count": 5,
                "leading_symbol": "sz300750",
                "leading_name": "宁德时代",
                "momentum_score": 58.2,
            }
        ],
        summary="情绪偏强，优先跟踪锂电池。",
        report_summary="测试报告摘要",
        generated_at=datetime(2026, 4, 24, 10, 30, tzinfo=UTC),
        started_at=datetime(2026, 4, 24, 10, 29, tzinfo=UTC),
        finished_at=datetime(2026, 4, 24, 10, 30, tzinfo=UTC),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    db.add(
        RecommendationItem(
            run_id=run.id,
            symbol="sz300750",
            code="300750",
            name="宁德时代",
            security_type="stock",
            risk="medium",
            score=82.5,
            strategy="trend_pullback",
            layer="pullback",
            sector="锂电池",
            sector_rank=1,
            price=220.5,
            change_pct=4.2,
            reasons=["趋势回调样本"],
            support_type="ma10",
            support_price=215.0,
            support_distance_pct=2.55,
            atr_stop_loss=208.0,
        )
    )
    db.commit()

    monkeypatch.setattr(market_api_module.overview_service, "get_overview", lambda: build_overview_read())

    overview_response = client.get("/api/v1/market/overview")
    latest_response = client.get("/api/v1/market/research/latest")
    recommendations_response = client.get("/api/v1/market/recommendations")
    history_response = client.get("/api/v1/market/research/history")

    assert overview_response.status_code == 200
    assert overview_response.json()["market_sentiment"]["title"] == "震荡分化"
    assert overview_response.json()["breadth_distribution"]["advancing_count"] == 2035
    assert overview_response.json()["turnover_summary"]["today_amount"] == 265760000000.0
    assert overview_response.json()["sector_momentum_top"][0]["sector"] == "锂电池"

    assert latest_response.status_code == 200
    assert latest_response.json()["snapshot"]["id"] == run.id
    assert latest_response.json()["items"][0]["strategy"] == "trend_pullback"

    assert recommendations_response.status_code == 200
    assert recommendations_response.json()[0]["run_id"] == run.id
    assert recommendations_response.json()[0]["support_type"] == "ma10"

    assert history_response.status_code == 200
    assert history_response.json()["runs"][0]["status"] == "succeeded"


def test_market_research_run_api_queues_task(client, db, monkeypatch) -> None:
    monkeypatch.setattr(
        market_api_module.run_market_research_task,
        "apply_async",
        lambda kwargs=None: SimpleNamespace(id="task-123"),
    )

    response = client.post("/api/v1/market/research/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["task_id"] == "task-123"

    latest_run = db.query(RecommendationRun).order_by(RecommendationRun.id.desc()).first()
    assert latest_run is not None
    assert latest_run.status == RecommendationRunStatus.QUEUED
    assert latest_run.task_id == "task-123"
