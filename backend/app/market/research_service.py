from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.market.history_service import HistoryService
from app.market.overview_service import MarketOverviewService
from app.market.research_config import (
    DEFAULT_RECOMMENDATION_COUNT,
    DEFAULT_RESEARCH_POOL,
    HISTORY_BAR_LIMIT,
    MAX_RECOMMENDATIONS_PER_SECTOR,
    MAX_RESEARCH_CANDIDATES,
    MIN_RECOMMENDATION_COUNT,
)
from app.market.service import QuoteService
from app.models.recommendation_item import RecommendationItem
from app.models.recommendation_run import RecommendationRun, RecommendationRunStatus
from app.schemas.market import (
    MarketOverviewRead,
    MarketQuoteRead,
    MarketRecommendationRead,
    MarketResearchLatestRead,
    MarketResearchRunRead,
    MarketSentimentRead,
    SectorMomentumRead,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CandidateSecurity:
    symbol: str
    code: str
    name: str
    sector: str
    source: str


@dataclass(slots=True)
class CandidateAnalysis:
    candidate: CandidateSecurity
    quote: MarketQuoteRead
    score: float
    strategy: str | None
    layer: str | None
    reasons: list[str]
    support_type: str | None
    support_price: float | None
    support_distance_pct: float | None
    atr_stop_loss: float | None
    risk: str
    sector_rank: int | None


class MarketResearchService:
    def __init__(
        self,
        overview_service: MarketOverviewService | None = None,
        quote_service: QuoteService | None = None,
        history_service: HistoryService | None = None,
    ) -> None:
        self.overview_service = overview_service or MarketOverviewService()
        self.quote_service = quote_service or QuoteService()
        self.history_service = history_service or HistoryService()

    def create_run(self, db: Session, *, triggered_by: str) -> RecommendationRun:
        run = RecommendationRun(
            triggered_by=triggered_by,
            status=RecommendationRunStatus.QUEUED,
            started_at=datetime.now(UTC),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def mark_run_queued(self, db: Session, run_id: int, *, task_id: str) -> RecommendationRun:
        run = db.get(RecommendationRun, run_id)
        if run is None:
            raise ValueError(f"Recommendation run {run_id} not found")
        run.task_id = task_id
        run.status = RecommendationRunStatus.QUEUED
        run.error_message = None
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def fail_run(self, db: Session, run_id: int, *, error_message: str) -> RecommendationRun:
        run = db.get(RecommendationRun, run_id)
        if run is None:
            raise ValueError(f"Recommendation run {run_id} not found")
        run.status = RecommendationRunStatus.FAILED
        run.error_message = error_message
        run.finished_at = datetime.now(UTC)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def execute_run(self, db: Session, *, run_id: int | None = None, task_id: str | None = None, triggered_by: str = "system") -> RecommendationRun:
        run = self._prepare_run(db, run_id=run_id, task_id=task_id, triggered_by=triggered_by)
        try:
            overview = self.overview_service.get_overview(force_refresh=True)
            candidates = self._build_candidate_pool(overview)
            quotes = self.quote_service.list_quotes([candidate.symbol for candidate in candidates], force_refresh=True)
            quote_map = {quote.symbol: quote for quote in quotes}
            histories = self.history_service.get_daily_bars_map(list(quote_map.keys()), limit=HISTORY_BAR_LIMIT)

            market_sentiment = self._build_market_sentiment(overview, list(quote_map.values()))
            sector_momentum = self._build_sector_momentum(candidates, quote_map)
            sector_rank_map = {item.sector: item.rank for item in sector_momentum}

            analyses: list[CandidateAnalysis] = []
            for candidate in candidates:
                quote = quote_map.get(candidate.symbol)
                if quote is None or quote.price is None:
                    continue
                analyses.append(
                    self._analyze_candidate(
                        db,
                        candidate=candidate,
                        quote=quote,
                        bars=histories.get(candidate.symbol, []),
                        sector_rank=sector_rank_map.get(candidate.sector),
                    )
                )

            selected = self._select_recommendations(analyses)
            summary = self._build_summary(market_sentiment, sector_momentum, selected)
            report_summary = self._build_report_summary(market_sentiment, sector_momentum, selected)

            run.status = RecommendationRunStatus.SUCCEEDED
            run.task_id = task_id or run.task_id
            run.candidate_pool_size = len(candidates)
            run.recommendation_count = len(selected)
            run.northbound_net_inflow = overview.northbound.net_inflow
            run.market_sentiment = market_sentiment.model_dump()
            run.sector_momentum_top = [item.model_dump() for item in sector_momentum[:5]]
            run.summary = summary
            run.report_summary = report_summary
            run.error_message = None
            run.generated_at = datetime.now(UTC)
            run.finished_at = datetime.now(UTC)
            db.add(run)
            db.flush()

            db.execute(delete(RecommendationItem).where(RecommendationItem.run_id == run.id))
            for analysis in selected:
                previous_item = self.get_previous_recommendation(db, analysis.candidate.symbol, before_run_id=run.id)
                item = RecommendationItem(
                    run_id=run.id,
                    symbol=analysis.candidate.symbol,
                    code=analysis.candidate.code,
                    name=analysis.candidate.name,
                    security_type="stock",
                    risk=analysis.risk,
                    score=round(analysis.score, 2),
                    strategy=analysis.strategy,
                    layer=analysis.layer,
                    sector=analysis.candidate.sector,
                    sector_rank=analysis.sector_rank,
                    price=analysis.quote.price,
                    change_pct=analysis.quote.change_percent,
                    reasons=analysis.reasons,
                    support_type=analysis.support_type,
                    support_price=analysis.support_price,
                    support_distance_pct=analysis.support_distance_pct,
                    atr_stop_loss=analysis.atr_stop_loss,
                    previous_recommendation_price=previous_item.price if previous_item else None,
                    previous_recommendation_at=previous_item.created_at if previous_item else None,
                )
                db.add(item)

            db.commit()
            db.refresh(run)
            return run
        except Exception as error:
            logger.exception("Market research run failed run_id=%s", run.id)
            run.status = RecommendationRunStatus.FAILED
            run.error_message = str(error)
            run.task_id = task_id or run.task_id
            run.finished_at = datetime.now(UTC)
            db.add(run)
            db.commit()
            db.refresh(run)
            raise

    def get_latest_snapshot(self, db: Session) -> MarketResearchLatestRead:
        latest_task = self._get_latest_run(db)
        snapshot_run = self._get_latest_successful_run(db)
        items = self.list_latest_recommendations(db)
        return MarketResearchLatestRead(
            snapshot=self._serialize_run(snapshot_run) if snapshot_run else None,
            items=items,
            latest_task=self._serialize_run(latest_task) if latest_task else None,
        )

    def list_history(self, db: Session, *, limit: int = 10) -> list[MarketResearchRunRead]:
        runs = db.scalars(
            select(RecommendationRun).order_by(desc(RecommendationRun.started_at), desc(RecommendationRun.id)).limit(limit)
        ).all()
        return [self._serialize_run(run) for run in runs]

    def list_latest_recommendations(self, db: Session) -> list[MarketRecommendationRead]:
        run = self._get_latest_successful_run(db)
        if run is None:
            return []
        items = db.scalars(
            select(RecommendationItem)
            .where(RecommendationItem.run_id == run.id)
            .order_by(desc(RecommendationItem.score), RecommendationItem.id)
        ).all()
        return [self._serialize_item(item) for item in items]

    def get_previous_recommendation(self, db: Session, symbol: str, *, before_run_id: int | None = None) -> RecommendationItem | None:
        query = (
            select(RecommendationItem)
            .join(RecommendationRun, RecommendationRun.id == RecommendationItem.run_id)
            .where(
                RecommendationItem.symbol == symbol,
                RecommendationRun.status == RecommendationRunStatus.SUCCEEDED,
            )
            .order_by(desc(RecommendationRun.generated_at), desc(RecommendationItem.id))
        )
        if before_run_id is not None:
            query = query.where(RecommendationItem.run_id < before_run_id)
        return db.scalar(query.limit(1))

    def augment_overview(self, overview: MarketOverviewRead, db: Session) -> MarketOverviewRead:
        run = self._get_latest_successful_run(db)
        if run is None:
            return overview
        if overview.market_sentiment is None:
            overview.market_sentiment = self._market_sentiment_from_payload(run.market_sentiment)
        if not overview.sector_momentum_top:
            overview.sector_momentum_top = [
                SectorMomentumRead.model_validate(item)
                for item in (run.sector_momentum_top or [])
                if isinstance(item, dict)
            ]
        return overview

    def _prepare_run(self, db: Session, *, run_id: int | None, task_id: str | None, triggered_by: str) -> RecommendationRun:
        if run_id is not None:
            run = db.get(RecommendationRun, run_id)
            if run is None:
                raise ValueError(f"Recommendation run {run_id} not found")
        else:
            run = RecommendationRun(triggered_by=triggered_by, started_at=datetime.now(UTC))
        run.status = RecommendationRunStatus.RUNNING
        run.task_id = task_id or run.task_id
        run.error_message = None
        run.started_at = run.started_at or datetime.now(UTC)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _build_candidate_pool(self, overview: MarketOverviewRead) -> list[CandidateSecurity]:
        candidates: list[CandidateSecurity] = []
        seen: set[str] = set()

        for item in DEFAULT_RESEARCH_POOL:
            symbol = item["symbol"]
            if symbol in seen:
                continue
            seen.add(symbol)
            candidates.append(
                CandidateSecurity(
                    symbol=symbol,
                    code=item["code"],
                    name=item["name"],
                    sector=item["sector"],
                    source="core_pool",
                )
            )

        for item in overview.hot_stocks:
            if item.symbol in seen or len(candidates) >= MAX_RESEARCH_CANDIDATES:
                continue
            seen.add(item.symbol)
            candidates.append(
                CandidateSecurity(
                    symbol=item.symbol,
                    code=item.code,
                    name=item.name,
                    sector=item.sector or "热点补充",
                    source="hot_stock",
                )
            )

        return candidates[:MAX_RESEARCH_CANDIDATES]

    def _build_market_sentiment(self, overview: MarketOverviewRead, quotes: list[MarketQuoteRead]) -> MarketSentimentRead:
        advancing_count = sum((quote.change_percent or 0.0) > 0 for quote in quotes)
        declining_count = sum((quote.change_percent or 0.0) < 0 for quote in quotes)
        flat_count = max(len(quotes) - advancing_count - declining_count, 0)
        limit_up_count = overview.limit_up.total
        limit_down_count = overview.limit_down.total
        breadth_ratio = (advancing_count + 1) / (declining_count + 1)
        northbound = overview.northbound.net_inflow

        score = 50.0
        score += min(max((breadth_ratio - 1.0) * 18, -18), 18)
        score += min(limit_up_count, 20) * 0.8
        score -= min(limit_down_count, 20) * 0.8
        if northbound is not None:
            score += max(min(northbound / 100000000, 8), -8)
        score = round(min(max(score, 0.0), 100.0), 2)

        if score >= 62:
            label = "strong"
            title = "情绪偏强"
            selection_mode = "momentum"
        elif score <= 42:
            label = "weak"
            title = "情绪偏弱"
            selection_mode = "defensive"
        else:
            label = "range"
            title = "震荡分化"
            selection_mode = "balanced"

        summary = f"上涨 {advancing_count} 家，下跌 {declining_count} 家，涨停 {limit_up_count} 家，跌停 {limit_down_count} 家。"

        return MarketSentimentRead(
            label=label,
            title=title,
            score=score,
            selection_mode=selection_mode,
            advancing_count=advancing_count,
            declining_count=declining_count,
            flat_count=flat_count,
            limit_up_count=limit_up_count,
            limit_down_count=limit_down_count,
            northbound_net_inflow=northbound,
            summary=summary,
        )

    def _build_sector_momentum(
        self,
        candidates: list[CandidateSecurity],
        quote_map: dict[str, MarketQuoteRead],
    ) -> list[SectorMomentumRead]:
        grouped: dict[str, list[tuple[CandidateSecurity, MarketQuoteRead]]] = {}
        for candidate in candidates:
            quote = quote_map.get(candidate.symbol)
            if quote is None or quote.change_percent is None:
                continue
            grouped.setdefault(candidate.sector, []).append((candidate, quote))

        ranked: list[SectorMomentumRead] = []
        for sector, entries in grouped.items():
            changes = [quote.change_percent or 0.0 for _, quote in entries]
            positive_ratio = sum(change > 0 for change in changes) / len(changes)
            momentum_score = round(mean(changes) * 8 + positive_ratio * 30 + len(entries), 2)
            leader_candidate, leader_quote = max(entries, key=lambda item: item[1].change_percent or -999)
            ranked.append(
                SectorMomentumRead(
                    sector=sector,
                    rank=0,
                    avg_change_pct=round(mean(changes), 2),
                    positive_ratio=round(positive_ratio, 2),
                    candidate_count=len(entries),
                    leading_symbol=leader_candidate.symbol,
                    leading_name=leader_candidate.name,
                    momentum_score=momentum_score,
                )
            )

        ranked.sort(key=lambda item: (-item.momentum_score, -item.avg_change_pct, item.sector))
        for index, item in enumerate(ranked, start=1):
            item.rank = index
        return ranked

    def _analyze_candidate(
        self,
        db: Session,
        *,
        candidate: CandidateSecurity,
        quote: MarketQuoteRead,
        bars: list,
        sector_rank: int | None,
    ) -> CandidateAnalysis:
        closes = [bar.close_price for bar in bars if bar.close_price > 0]
        highs = [bar.high_price for bar in bars if bar.high_price > 0]
        lows = [bar.low_price for bar in bars if bar.low_price > 0]

        ma5 = self._moving_average(closes, 5)
        ma10 = self._moving_average(closes, 10)
        ma20 = self._moving_average(closes, 20)
        recent_high = max(highs[-20:], default=quote.price or 0.0)
        recent_low = min(lows[-20:], default=quote.price or 0.0)
        atr = self._atr(bars, 14)
        support_type, support_price, support_distance_pct = self._support_level(
            current_price=quote.price or 0.0,
            ma10=ma10,
            ma20=ma20,
            recent_low=recent_low,
        )

        strategy: str | None = None
        layer: str | None = None
        score = 35.0
        reasons: list[str] = []
        current_price = quote.price or 0.0
        change_pct = quote.change_percent or 0.0
        sector_bonus = max(0, 6 - (sector_rank or 6))

        drawdown_from_high_pct = ((current_price / recent_high) - 1) * 100 if recent_high > 0 else 0.0
        rebound_from_low_pct = ((current_price / recent_low) - 1) * 100 if recent_low > 0 else 0.0

        if drawdown_from_high_pct <= -12 and support_distance_pct is not None and support_distance_pct <= 4.5:
            strategy = "oversold_reversal"
            layer = "oversold"
            score = 62 + abs(drawdown_from_high_pct) * 0.8 + sector_bonus
            reasons.append(f"距 20 日高点回撤 {abs(drawdown_from_high_pct):.2f}% ，进入超跌观察区。")
            if support_type and support_price is not None:
                reasons.append(f"当前价靠近 {support_type} 支撑 {support_price:.2f} 。")
        elif ma20 and current_price >= ma20 and drawdown_from_high_pct <= -4 and change_pct > -2.5:
            strategy = "trend_pullback"
            layer = "pullback"
            score = 58 + max(change_pct, 0) * 2 + sector_bonus
            reasons.append("价格仍位于中期均线之上，属于强势趋势中的回调观察位。")
            if ma10:
                reasons.append(f"10 日均线约 {ma10:.2f} ，适合跟踪回踩后的承接力度。")
        elif support_distance_pct is not None and support_distance_pct <= 2.8:
            strategy = "support_retest"
            layer = "support"
            score = 52 + max(0, 3 - support_distance_pct) * 4 + sector_bonus
            reasons.append("价格接近支撑位，适合做支撑有效性跟踪。")
            if rebound_from_low_pct > 0:
                reasons.append(f"相对近 20 日低点已回升 {rebound_from_low_pct:.2f}% 。")
        else:
            score = 40 + max(0, 2 - abs(change_pct)) * 2 + sector_bonus
            if change_pct > 0:
                reasons.append("波动尚可，但暂未进入更明确的规则分层。")
            else:
                reasons.append("结构尚不充分，先放入观察名单。")

        previous_item = self.get_previous_recommendation(db, candidate.symbol)
        if previous_item and previous_item.price and current_price > 0:
            since_last_pct = ((current_price / previous_item.price) - 1) * 100
            reasons.append(f"相对上次推荐位变动 {since_last_pct:+.2f}% ，可用于回看强弱延续。")

        atr_stop_loss = round(max(current_price - atr * 1.5, 0), 2) if atr > 0 else None
        risk = self._risk_label(layer=layer, change_pct=change_pct, support_distance_pct=support_distance_pct)

        return CandidateAnalysis(
            candidate=candidate,
            quote=quote,
            score=round(score, 2),
            strategy=strategy,
            layer=layer,
            reasons=reasons,
            support_type=support_type,
            support_price=round(support_price, 2) if support_price else None,
            support_distance_pct=round(support_distance_pct, 2) if support_distance_pct is not None else None,
            atr_stop_loss=atr_stop_loss,
            risk=risk,
            sector_rank=sector_rank,
        )

    def _select_recommendations(self, analyses: list[CandidateAnalysis]) -> list[CandidateAnalysis]:
        analyses.sort(
            key=lambda item: (
                item.layer is None,
                -item.score,
                item.sector_rank or 999,
                item.candidate.code,
            )
        )

        selected: list[CandidateAnalysis] = []
        sector_counts: dict[str, int] = {}

        for analysis in analyses:
            if len(selected) >= DEFAULT_RECOMMENDATION_COUNT:
                break
            if analysis.layer is None and len(selected) >= MIN_RECOMMENDATION_COUNT:
                continue
            if sector_counts.get(analysis.candidate.sector, 0) >= MAX_RECOMMENDATIONS_PER_SECTOR:
                continue
            selected.append(analysis)
            sector_counts[analysis.candidate.sector] = sector_counts.get(analysis.candidate.sector, 0) + 1

        if len(selected) < MIN_RECOMMENDATION_COUNT:
            extras = [item for item in analyses if item not in selected]
            for analysis in extras:
                if len(selected) >= MIN_RECOMMENDATION_COUNT:
                    break
                selected.append(analysis)

        return selected[:DEFAULT_RECOMMENDATION_COUNT]

    @staticmethod
    def _build_summary(
        sentiment: MarketSentimentRead,
        sector_momentum: list[SectorMomentumRead],
        analyses: list[CandidateAnalysis],
    ) -> str:
        sector_summary = "、".join(item.sector for item in sector_momentum[:3]) or "暂无明显主线"
        return f"{sentiment.title}，当前优先跟踪 {sector_summary}，本次输出 {len(analyses)} 条规则研究候选。"

    @staticmethod
    def _build_report_summary(
        sentiment: MarketSentimentRead,
        sector_momentum: list[SectorMomentumRead],
        analyses: list[CandidateAnalysis],
    ) -> str:
        layer_counts = {
            "oversold": sum(item.layer == "oversold" for item in analyses),
            "support": sum(item.layer == "support" for item in analyses),
            "pullback": sum(item.layer == "pullback" for item in analyses),
        }
        sector_summary = "、".join(item.sector for item in sector_momentum[:3]) or "暂无"
        return (
            f"市场处于{sentiment.title}阶段，筛选模式为 {sentiment.selection_mode}。"
            f"板块热度前排为 {sector_summary}。"
            f"推荐结构为超跌 {layer_counts['oversold']} 条、支撑 {layer_counts['support']} 条、回调 {layer_counts['pullback']} 条。"
        )

    @staticmethod
    def _moving_average(values: list[float], window: int) -> float | None:
        if len(values) < window:
            return None
        return round(sum(values[-window:]) / window, 4)

    @staticmethod
    def _atr(bars: list, window: int) -> float:
        if len(bars) < 2:
            return 0.0
        recent_bars = bars[-window:]
        true_ranges: list[float] = []
        previous_close = recent_bars[0].close_price
        for bar in recent_bars:
            true_ranges.append(
                max(
                    bar.high_price - bar.low_price,
                    abs(bar.high_price - previous_close),
                    abs(bar.low_price - previous_close),
                )
            )
            previous_close = bar.close_price
        return round(sum(true_ranges) / len(true_ranges), 4) if true_ranges else 0.0

    @staticmethod
    def _support_level(
        *,
        current_price: float,
        ma10: float | None,
        ma20: float | None,
        recent_low: float,
    ) -> tuple[str | None, float | None, float | None]:
        if current_price <= 0:
            return None, None, None

        candidates: list[tuple[str, float, float]] = []
        if ma10:
            candidates.append(("ma10", ma10, abs(current_price - ma10) / current_price * 100))
        if ma20:
            candidates.append(("ma20", ma20, abs(current_price - ma20) / current_price * 100))
        if recent_low > 0:
            candidates.append(("swing_low", recent_low, abs(current_price - recent_low) / current_price * 100))
        if not candidates:
            return None, None, None
        support_type, support_price, distance = min(candidates, key=lambda item: item[2])
        return support_type, support_price, distance

    @staticmethod
    def _risk_label(*, layer: str | None, change_pct: float, support_distance_pct: float | None) -> str:
        if layer == "pullback" and (support_distance_pct or 0) <= 2:
            return "low"
        if layer == "oversold" or abs(change_pct) >= 5 or (support_distance_pct or 0) > 4:
            return "high"
        return "medium"

    def _serialize_run(self, run: RecommendationRun) -> MarketResearchRunRead:
        return MarketResearchRunRead(
            id=run.id,
            task_id=run.task_id,
            status=run.status.value,
            triggered_by=run.triggered_by,
            candidate_pool_size=run.candidate_pool_size,
            recommendation_count=run.recommendation_count,
            northbound_net_inflow=run.northbound_net_inflow,
            summary=run.summary,
            report_summary=run.report_summary,
            error_message=run.error_message,
            generated_at=run.generated_at.isoformat() if run.generated_at else None,
            started_at=run.started_at.isoformat(),
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
            market_sentiment=self._market_sentiment_from_payload(run.market_sentiment),
            sector_momentum_top=[
                SectorMomentumRead.model_validate(item)
                for item in (run.sector_momentum_top or [])
                if isinstance(item, dict)
            ],
        )

    @staticmethod
    def _serialize_item(item: RecommendationItem) -> MarketRecommendationRead:
        reasons = [str(reason) for reason in (item.reasons or [])]
        return MarketRecommendationRead(
            symbol=item.symbol,
            code=item.code,
            name=item.name,
            type="stock" if item.security_type != "etf" else "etf",
            risk=item.risk,
            reason=reasons[0] if reasons else "规则研究快照",
            price=item.price,
            change_pct=item.change_pct,
            source="research_snapshot",
            score=item.score,
            strategy=item.strategy,
            layer=item.layer,
            sector=item.sector,
            sector_rank=item.sector_rank,
            reasons=reasons,
            support_type=item.support_type,
            support_price=item.support_price,
            support_distance_pct=item.support_distance_pct,
            atr_stop_loss=item.atr_stop_loss,
            run_id=item.run_id,
            previous_recommendation_price=item.previous_recommendation_price,
            previous_recommendation_at=item.previous_recommendation_at.isoformat() if item.previous_recommendation_at else None,
        )

    @staticmethod
    def _market_sentiment_from_payload(payload: dict | None) -> MarketSentimentRead | None:
        if not payload:
            return None
        return MarketSentimentRead.model_validate(payload)

    @staticmethod
    def _get_latest_run(db: Session) -> RecommendationRun | None:
        return db.scalar(select(RecommendationRun).order_by(desc(RecommendationRun.started_at), desc(RecommendationRun.id)).limit(1))

    @staticmethod
    def _get_latest_successful_run(db: Session) -> RecommendationRun | None:
        return db.scalar(
            select(RecommendationRun)
            .where(RecommendationRun.status == RecommendationRunStatus.SUCCEEDED)
            .order_by(desc(RecommendationRun.generated_at), desc(RecommendationRun.id))
            .limit(1)
        )
