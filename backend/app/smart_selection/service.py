from __future__ import annotations

import json
import logging
import math
import re
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import mean, pstdev

import httpx
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.market.history_service import HistoryService
from app.market.providers.base import DailyBarSnapshot
from app.models.smart_selection_config import SmartSelectionConfig
from app.models.smart_selection_item import SmartSelectionItem
from app.models.smart_selection_run import SmartSelectionRun, SmartSelectionRunStatus
from app.models.watchlist import WatchlistItem
from app.schemas.smart_selection import (
    SmartSelectionConfigRead,
    SmartSelectionConfigUpdate,
    SmartSelectionItemRead,
    SmartSelectionLatestRead,
    SmartSelectionRunRead,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "reference" / "智能选股" / "config.json"
SINA_QUOTE_URL = "http://hq.sinajs.cn/list="
SINA_KLINE_URL = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
SINA_SECTOR_URL = "http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
SINA_RATING_HEADERS = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
SINA_QUOTE_HEADERS = {"Referer": "http://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}


@dataclass(slots=True)
class DragonTigerSignal:
    tag: str
    score_delta: float
    signals: list[str]
    detail: dict[str, object]


class DragonTigerAnalyzer:
    def __init__(self, config: dict) -> None:
        lhb_keywords = config.get("lhb_keywords", {})
        self.black_keywords = [str(item) for item in lhb_keywords.get("black", [])]
        self.red_keywords = [str(item) for item in lhb_keywords.get("white", [])]
        self.config = config
        self.black_stocks: dict[str, list[dict[str, float | str]]] = {}
        self.red_stocks: dict[str, list[dict[str, float | str]]] = {}
        self.black_seats: list[dict[str, float | str]] = []
        self.red_seats: list[dict[str, float | str]] = []
        self.trade_date: str | None = None
        self.enabled = True

    def fetch(self) -> bool:
        try:
            import akshare as ak  # type: ignore
        except Exception:
            self.enabled = False
            return False

        lookback_days = int(self.config.get("lhb", {}).get("lookback_days", 3))
        for trade_date in self._recent_trade_dates(max(lookback_days, 1)):
            try:
                dataframe = ak.stock_lhb_hyyyb_em(start_date=trade_date, end_date=trade_date)
            except Exception as error:
                logger.warning("Smart selection LHB fetch failed date=%s error=%s", trade_date, error)
                continue
            if dataframe is None or getattr(dataframe, "empty", False):
                continue
            try:
                self._ingest_dataframe(dataframe)
            except Exception as error:
                logger.warning("Smart selection LHB parse failed date=%s error=%s", trade_date, error)
                continue
            self.trade_date = trade_date
            return True

        self.enabled = False
        return False

    def classify(self, stock_name: str) -> DragonTigerSignal:
        red_entries = self._find_entries(self.red_stocks, stock_name)
        black_entries = self._find_entries(self.black_stocks, stock_name)
        red_net = sum(float(item["net"]) for item in red_entries)
        black_net = sum(float(item["net"]) for item in black_entries)
        detail = {
            "trade_date": self.trade_date,
            "red_net": round(red_net, 2),
            "black_net": round(black_net, 2),
            "confidence": "neutral",
            "source_enabled": self.enabled,
        }

        if black_entries and black_net >= red_net:
            detail["confidence"] = "negative"
            return DragonTigerSignal(
                tag="BLACK",
                score_delta=-abs(float(self.config.get("scoring", {}).get("lhb_black_penalty", 100))),
                signals=[f"黑榜资金压制:{black_net / 1e4:.0f}W"],
                detail=detail,
            )

        if red_entries:
            bonus = float(self.config.get("scoring", {}).get("lhb_red_bonus", 10))
            if red_net > 1e8:
                detail["confidence"] = "high"
                return DragonTigerSignal(
                    tag="RED",
                    score_delta=bonus,
                    signals=[f"红榜资金强化:{red_net / 1e8:.2f}亿"],
                    detail=detail,
                )
            if red_net > 5e7:
                detail["confidence"] = "medium"
                return DragonTigerSignal(
                    tag="RED",
                    score_delta=bonus * 0.7,
                    signals=[f"红榜资金确认:{red_net / 1e7:.0f}千万"],
                    detail=detail,
                )
            detail["confidence"] = "low"
            return DragonTigerSignal(
                tag="RED",
                score_delta=bonus * 0.4,
                signals=["红榜席位轻度加分"],
                detail=detail,
            )

        return DragonTigerSignal(tag="N/A", score_delta=0.0, signals=[], detail=detail)

    def _ingest_dataframe(self, dataframe) -> None:
        seat_col = self._pick_column(dataframe.columns, ("营业部", "席位"))
        net_col = self._pick_column(dataframe.columns, ("净买", "净额"))
        stock_col = self._pick_column(dataframe.columns, ("股票",))
        if seat_col is None or stock_col is None:
            raise ValueError("missing dragon tiger columns")

        for _, row in dataframe.iterrows():
            seat = str(row.get(seat_col, "")).strip()
            stock_value = str(row.get(stock_col, "")).strip()
            if not seat or not stock_value or stock_value.lower() == "nan":
                continue

            net = self._parse_float(row.get(net_col, 0.0)) if net_col else 0.0
            stock_list = [item.strip() for item in re.split(r"[\s、,，;/]+", stock_value) if item.strip()]
            black_hit = next((keyword for keyword in self.black_keywords if keyword in seat), "")
            white_hit = next((keyword for keyword in self.red_keywords if keyword in seat), "")

            if black_hit:
                self.black_seats.append({"seat": seat, "net": net, "stocks": " ".join(stock_list), "tag": black_hit})
                for stock_name in stock_list:
                    self.black_stocks.setdefault(stock_name, []).append({"seat": seat, "net": net})
            elif white_hit:
                self.red_seats.append({"seat": seat, "net": net, "stocks": " ".join(stock_list), "tag": white_hit})
                for stock_name in stock_list:
                    self.red_stocks.setdefault(stock_name, []).append({"seat": seat, "net": net})

    @staticmethod
    def _pick_column(columns, keywords: tuple[str, ...]) -> str | None:
        for column in columns:
            column_text = str(column)
            if any(keyword in column_text for keyword in keywords):
                return column_text
        return None

    @staticmethod
    def _parse_float(value: object) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).replace(",", "").replace("，", "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group()) if match else 0.0

    @staticmethod
    def _find_entries(store: dict[str, list[dict[str, float | str]]], stock_name: str) -> list[dict[str, float | str]]:
        results: list[dict[str, float | str]] = []
        for name, entries in store.items():
            if name in stock_name or stock_name in name:
                results.extend(entries)
        return results

    @staticmethod
    def _recent_trade_dates(days: int) -> list[str]:
        dates: list[str] = []
        current = datetime.now(UTC)
        seen: set[str] = set()
        for delta in range(max(days, 1) + 10):
            target = current - timedelta(days=delta)
            if target.weekday() >= 5:
                continue
            trade_date = target.strftime("%Y%m%d")
            if trade_date not in seen:
                seen.add(trade_date)
                dates.append(trade_date)
            if len(dates) >= days:
                break
        return dates


class SmartSelectionService:
    def __init__(self, history_service: HistoryService | None = None) -> None:
        self.history_service = history_service or HistoryService()

    def get_config(self, db: Session, tenant_id: str) -> SmartSelectionConfigRead:
        return self._serialize_config(self._ensure_config(db, tenant_id))

    def update_config(self, db: Session, tenant_id: str, payload: SmartSelectionConfigUpdate) -> SmartSelectionConfigRead:
        config = self._ensure_config(db, tenant_id)
        if payload.enabled is not None:
            config.enabled = payload.enabled
        if payload.config_payload is not None:
            config.config_payload = self._normalize_config_payload(payload.config_payload)
        config.schedule_time = "20:00"
        db.add(config)
        db.commit()
        db.refresh(config)
        return self._serialize_config(config)

    def create_run(self, db: Session, *, tenant_id: str, triggered_by: str) -> SmartSelectionRun:
        config = self._ensure_config(db, tenant_id)
        run = SmartSelectionRun(
            tenant_id=tenant_id,
            triggered_by=triggered_by,
            status=SmartSelectionRunStatus.QUEUED,
            started_at=datetime.now(UTC),
            config_snapshot=deepcopy(config.config_payload),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def mark_run_queued(self, db: Session, run_id: int, *, task_id: str) -> SmartSelectionRun:
        run = db.get(SmartSelectionRun, run_id)
        if run is None:
            raise ValueError(f"Smart selection run {run_id} not found")
        run.task_id = task_id
        run.status = SmartSelectionRunStatus.QUEUED
        run.error_message = None
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def fail_run(self, db: Session, run_id: int, *, error_message: str) -> SmartSelectionRun:
        run = db.get(SmartSelectionRun, run_id)
        if run is None:
            raise ValueError(f"Smart selection run {run_id} not found")
        run.status = SmartSelectionRunStatus.FAILED
        run.error_message = error_message
        run.finished_at = datetime.now(UTC)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def execute_run(
        self,
        db: Session,
        *,
        run_id: int | None = None,
        task_id: str | None = None,
        triggered_by: str = "system",
        tenant_id: str = "local",
    ) -> SmartSelectionRun:
        run, config = self._prepare_run(
            db,
            run_id=run_id,
            task_id=task_id,
            triggered_by=triggered_by,
            tenant_id=tenant_id,
        )
        runtime_config = deepcopy(config.config_payload)

        try:
            if not config.enabled and triggered_by != "manual":
                logger.info("Smart selection run skipped run_id=%s tenant_id=%s reason=disabled", run.id, tenant_id)
                run.status = SmartSelectionRunStatus.SUCCEEDED
                run.summary = "智能选股已停用，定时任务本次跳过。"
                run.report_body = "当前基础偏好为停用状态，仅记录本次调度跳过。"
                run.generated_at = None
                run.finished_at = datetime.now(UTC)
                db.add(run)
                db.commit()
                db.refresh(run)
                return run

            logger.info("Smart selection run executing run_id=%s tenant_id=%s phase=market", run.id, tenant_id)
            market = self._get_market_index()
            hot_sectors = self._get_hot_sectors()
            market_state = self._assess_market_regime(market, hot_sectors)
            logger.info(
                "Smart selection run market ready run_id=%s regime=%s indices=%s sectors=%s",
                run.id,
                market_state.get("regime"),
                len(market),
                len(hot_sectors),
            )

            logger.info("Smart selection run executing run_id=%s tenant_id=%s phase=dragon_tiger", run.id, tenant_id)
            lhb = DragonTigerAnalyzer(runtime_config)
            lhb.fetch()
            logger.info("Smart selection run dragon_tiger ready run_id=%s enabled=%s", run.id, lhb.enabled)

            logger.info("Smart selection run executing run_id=%s tenant_id=%s phase=candidate_pool", run.id, tenant_id)
            spots, pool_summary = self._build_candidate_pool(db, tenant_id, runtime_config)
            logger.info(
                "Smart selection run candidate_pool ready run_id=%s watchlist=%s institution=%s candidates=%s",
                run.id,
                pool_summary.get("watchlist_count", 0),
                pool_summary.get("institution_pool_count", 0),
                pool_summary.get("final_candidate_count", 0),
            )

            logger.info("Smart selection run executing run_id=%s tenant_id=%s phase=scoring", run.id, tenant_id)
            results, excluded_by_lhb = self._score_candidates(spots, hot_sectors, market_state, lhb, runtime_config)
            logger.info(
                "Smart selection run scoring ready run_id=%s recommended=%s excluded_by_lhb=%s",
                run.id,
                len(results),
                len(excluded_by_lhb),
            )

            logger.info("Smart selection run executing run_id=%s tenant_id=%s phase=report", run.id, tenant_id)
            position_advice = self._build_position_advice(results, market_state, runtime_config)
            report_body = self._generate_markdown_report(
                lhb=lhb if lhb.enabled else None,
                market=market,
                market_state=market_state,
                hot_sectors=hot_sectors,
                pool_summary=pool_summary,
                results=results,
                excluded_by_lhb=excluded_by_lhb,
                spots=spots,
                position_advice=position_advice,
            )

            run.status = SmartSelectionRunStatus.SUCCEEDED
            run.task_id = task_id or run.task_id
            run.candidate_pool_size = pool_summary.get("final_candidate_count", 0)
            run.recommendation_count = len(results)
            run.summary = self._build_summary(market_state, results, pool_summary)
            run.report_body = report_body
            run.error_message = None
            run.generated_at = datetime.now(UTC)
            run.finished_at = datetime.now(UTC)
            run.config_snapshot = deepcopy(runtime_config)
            db.add(run)
            db.flush()

            db.execute(delete(SmartSelectionItem).where(SmartSelectionItem.run_id == run.id))
            for result in results:
                db.add(
                    SmartSelectionItem(
                        run_id=run.id,
                        symbol=self._normalize_symbol(result["code"]) or result["code"],
                        code=result["code"],
                        name=result["name"],
                        score=float(result["score"]),
                        price=float(result["price"]),
                        change_pct=float(result["change"]),
                        target_price=float(result["target"]),
                        stop_loss_price=float(result["stop"]),
                        tags=self._build_item_tags(result),
                        reason="；".join(result.get("signals", [])[:6]) or result["timing"],
                        dimension_scores=result.get("dim", {}),
                        raw_detail=result,
                    )
                )

            db.commit()
            db.refresh(run)
            logger.info(
                "Smart selection run persisted run_id=%s status=%s recommendations=%s candidates=%s",
                run.id,
                run.status.value,
                run.recommendation_count,
                run.candidate_pool_size,
            )
            return run
        except Exception as error:
            logger.exception("Smart selection run failed run_id=%s", run.id)
            run.status = SmartSelectionRunStatus.FAILED
            run.error_message = str(error)
            run.task_id = task_id or run.task_id
            run.finished_at = datetime.now(UTC)
            db.add(run)
            db.commit()
            db.refresh(run)
            raise

    def get_latest_snapshot(self, db: Session, tenant_id: str) -> SmartSelectionLatestRead:
        latest_task = self._get_latest_run(db, tenant_id)
        latest_success = self._get_latest_successful_run(db, tenant_id)
        items = self.list_latest_items(db, tenant_id)
        return SmartSelectionLatestRead(
            snapshot=self._serialize_run(latest_success) if latest_success else None,
            items=items,
            latest_task=self._serialize_run(latest_task) if latest_task else None,
        )

    def list_history(self, db: Session, tenant_id: str, *, limit: int = 10) -> list[SmartSelectionRunRead]:
        runs = db.scalars(
            select(SmartSelectionRun)
            .where(SmartSelectionRun.tenant_id == tenant_id)
            .order_by(desc(SmartSelectionRun.started_at), desc(SmartSelectionRun.id))
            .limit(limit)
        ).all()
        return [self._serialize_run(run) for run in runs]

    def list_latest_items(self, db: Session, tenant_id: str) -> list[SmartSelectionItemRead]:
        run = self._get_latest_successful_run(db, tenant_id)
        if run is None:
            return []
        items = db.scalars(
            select(SmartSelectionItem)
            .where(SmartSelectionItem.run_id == run.id)
            .order_by(desc(SmartSelectionItem.score), SmartSelectionItem.id)
        ).all()
        return [self._serialize_item(item) for item in items]

    def _prepare_run(
        self,
        db: Session,
        *,
        run_id: int | None,
        task_id: str | None,
        triggered_by: str,
        tenant_id: str,
    ) -> tuple[SmartSelectionRun, SmartSelectionConfig]:
        config = self._ensure_config(db, tenant_id)
        if run_id is not None:
            run = db.get(SmartSelectionRun, run_id)
            if run is None:
                raise ValueError(f"Smart selection run {run_id} not found")
        else:
            run = SmartSelectionRun(tenant_id=tenant_id, triggered_by=triggered_by, started_at=datetime.now(UTC))
        run.tenant_id = tenant_id
        run.triggered_by = triggered_by
        run.status = SmartSelectionRunStatus.RUNNING
        run.task_id = task_id or run.task_id
        run.error_message = None
        run.finished_at = None
        run.config_snapshot = deepcopy(config.config_payload)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run, config

    def _build_candidate_pool(self, db: Session, tenant_id: str, config: dict) -> tuple[dict[str, dict], dict]:
        pool_config = config.get("candidate_pool", {})
        batch_size = int(pool_config.get("batch_size", 50))
        watchlist_codes = self._list_watchlist_codes(db, tenant_id)
        institution_rows, institution_stats = self._fetch_institution_rating_pool(config)

        source_codes = [row["code"] for row in institution_rows]
        source_codes.extend(watchlist_codes)

        deduped_codes: list[str] = []
        seen: set[str] = set()
        for code in source_codes:
            normalized_code = str(code).zfill(6)
            if normalized_code in seen:
                continue
            seen.add(normalized_code)
            deduped_codes.append(normalized_code)

        spots = self._get_spot_batch(deduped_codes, batch_size=batch_size)
        for row in institution_rows:
            quote = spots.get(row["code"])
            if quote:
                row["latest_price"] = f"{quote['price']:.3f}" if quote["price"] < 100 else f"{quote['price']:.2f}"
                row["change_pct"] = f"{quote['change']:+.2f}%"

        summary = {
            "mode": "institution_watchlist",
            "watchlist_count": len(watchlist_codes),
            "institution_pool_count": institution_stats.get("final_pool_size", 0),
            "institution_pool_stats": institution_stats,
            "institution_pool_rows": institution_rows,
            "final_candidate_count": len(spots),
        }
        return spots, summary

    def _score_candidates(
        self,
        spots: dict[str, dict],
        hot_sectors: list[dict],
        market_state: dict,
        lhb: DragonTigerAnalyzer,
        config: dict,
    ) -> tuple[list[dict], list[dict]]:
        results: list[dict] = []
        excluded_by_lhb: list[dict] = []
        sector_map = {sector["name"]: sector for sector in hot_sectors}

        price_range = config.get("price_range", [0, 999999])
        min_volume = float(config.get("min_volume", 1))
        min_price = float(price_range[0]) if len(price_range) > 0 else 0.0
        max_price = float(price_range[1]) if len(price_range) > 1 else float("inf")

        for code, spot in spots.items():
            name = spot["name"]
            if "ST" in name or "*ST" in name:
                continue
            if spot["price"] < min_price or spot["price"] > max_price:
                continue
            if spot["change"] >= 9.5 or spot["change"] <= -9.5:
                continue
            if spot.get("amount", 0) < min_volume:
                continue

            lhb_signal = DragonTigerSignal(tag="N/A", score_delta=0.0, signals=[], detail={"confidence": "neutral"})
            if lhb.enabled:
                lhb_signal = lhb.classify(name)
                if lhb_signal.tag == "BLACK":
                    excluded_by_lhb.append(
                        {"code": code, "name": name, "reason": lhb_signal.signals[0] if lhb_signal.signals else "LHB Black"}
                    )
                    continue

            symbol = self._normalize_symbol(code)
            if symbol is None:
                continue
            bars = self._get_kline_bars(symbol, 320)
            tech = self._analyze_tech(bars, market_state, config)
            if not tech["valid"]:
                continue

            total_score, signals, dim = self._score_stock(spot, tech, lhb_signal, market_state, sector_map, config)
            trade_plan = self._calc_trade_plan(spot["price"], tech, market_state, config)
            if trade_plan["risk_reward"] < float(config.get("risk_control", {}).get("min_risk_reward", 1.0)):
                total_score -= 8
                signals.append("风险收益比不足，降权处理")

            timing = self._decide_timing(total_score, trade_plan["risk_reward"], market_state, config)
            if timing == "PASS":
                continue

            position_pct = min(
                float(config.get("risk_control", {}).get("max_position_pct", 18)),
                12 if timing == "STRONG BUY" else 8 if timing == "BUY" else 5,
            )

            spot_sectors = [sector_name for sector_name in sector_map if sector_name in name or name in sector_name]
            results.append(
                {
                    "symbol": symbol,
                    "code": code,
                    "name": name,
                    "price": round(spot["price"], 2),
                    "change": round(spot["change"], 2),
                    "amount": round(spot.get("amount", 0), 2),
                    "score": round(total_score, 1),
                    "timing": timing,
                    "target": trade_plan["target"],
                    "stop": trade_plan["stop"],
                    "risk_reward": trade_plan["risk_reward"],
                    "position_pct": position_pct,
                    "invalid_condition": trade_plan["invalid_condition"],
                    "signals": list(dict.fromkeys(signals + lhb_signal.signals)),
                    "dim": dim,
                    "lhb_tag": lhb_signal.tag,
                    "lhb_detail": lhb_signal.detail,
                    "hot_sectors": spot_sectors,
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[: int(config.get("max_recommendations", 10))], excluded_by_lhb

    def _fetch_institution_rating_pool(self, config: dict) -> tuple[list[dict], dict]:
        pool_cfg = config.get("institution_rating_pool", {})
        if not pool_cfg.get("enabled", False):
            return [], {
                "enabled": False,
                "pages_fetched": 0,
                "total_rows": 0,
                "deduped_rows": 0,
                "final_pool_size": 0,
                "source": "disabled",
            }

        max_pages = int(pool_cfg.get("pages", 50))
        allowed_ratings = set(pool_cfg.get("allowed_ratings", ["买入"]))
        max_count = int(pool_cfg.get("max_count", 1000))
        request_interval = float(pool_cfg.get("request_interval_ms", 300)) / 1000
        source_url = str(pool_cfg.get("source_url", ""))
        require_target_price = bool(pool_cfg.get("require_target_price", True))

        all_rows: list[dict] = []
        pages_fetched = 0
        latest_date: str | None = None

        for page in range(1, max_pages + 1):
            page_url = re.sub(r"p=\d+", f"p={page}", source_url) if "p=" in source_url else f"{source_url}&p={page}"
            try:
                response = self._http_get(page_url, headers=SINA_RATING_HEADERS, timeout=15)
            except Exception as error:
                logger.warning("Institution rating page fetch failed page=%s error=%s", page, error)
                break
            pages_fetched += 1
            page_rows = self._extract_rating_rows(response.text, page_url, allowed_ratings, require_target_price)
            if not page_rows:
                break
            if latest_date is None:
                latest_date = max(row["rating_date"] for row in page_rows)
            filtered_rows = [row for row in page_rows if row["rating_date"] == latest_date]
            if not filtered_rows:
                break
            all_rows.extend(filtered_rows)
            time.sleep(request_interval)

        by_code: dict[str, dict] = {}
        for row in all_rows:
            key = row["code"]
            if key not in by_code:
                current = dict(row)
                current["institutions"] = [row["institution"]]
                current["industries"] = [row.get("industry", "")] if row.get("industry", "") else []
                current["target_price_float"] = self._safe_float(row.get("target_price"), float("inf"))
                by_code[key] = current
                continue

            existing = by_code[key]
            if row["institution"] not in existing["institutions"]:
                existing["institutions"].append(row["institution"])
            industry = row.get("industry", "")
            if industry and industry not in existing["industries"]:
                existing["industries"].append(industry)
            existing["recommend_count"] = existing.get("recommend_count", 1) + 1
            current_target = self._safe_float(row.get("target_price"), float("inf"))
            if current_target < existing.get("target_price_float", float("inf")):
                existing["target_price"] = row.get("target_price")
                existing["target_price_float"] = current_target

        deduped_rows = list(by_code.values())
        for row in deduped_rows:
            row.pop("target_price_float", None)
        deduped_rows.sort(key=lambda row: (row.get("recommend_count", 1), row["rating_date"], row["code"]), reverse=True)
        deduped_rows = deduped_rows[:max_count]
        stats = {
            "enabled": True,
            "source": "institution_rating",
            "pages_fetched": pages_fetched,
            "total_rows": len(all_rows),
            "deduped_rows": len(deduped_rows),
            "duplicates_removed": max(0, len(all_rows) - len(deduped_rows)),
            "final_pool_size": len(deduped_rows),
            "latest_rating_date": latest_date,
            "lookback_days": int(pool_cfg.get("lookback_days", 2)),
        }
        return deduped_rows, stats

    def _get_spot_batch(self, codes: list[str], batch_size: int = 50) -> dict[str, dict]:
        result: dict[str, dict] = {}
        clean_codes = [code for code in codes if code and len(code) == 6]
        for index in range(0, len(clean_codes), batch_size):
            batch = clean_codes[index : index + batch_size]
            symbols = [self._normalize_symbol(code) for code in batch]
            normalized_symbols = [symbol for symbol in symbols if symbol]
            if not normalized_symbols:
                continue
            try:
                response = self._http_get(f"{SINA_QUOTE_URL}{','.join(normalized_symbols)}", headers=SINA_QUOTE_HEADERS, timeout=15)
            except Exception as error:
                logger.warning("Spot batch fetch failed batch=%s error=%s", batch, error)
                continue

            for line in response.text.strip().split("\n"):
                if "var hq_str_" not in line or '=""' in line:
                    continue
                try:
                    symbol = line.split("_str_")[1].split("=")[0]
                    data = line.split('"')[1].split(",")
                    if len(data) < 32:
                        continue
                    code = symbol[2:]
                    price = float(data[3])
                    previous_close = float(data[2])
                    change = (price - previous_close) / previous_close * 100 if previous_close > 0 else 0
                    volume = float(data[9])
                    amount = volume * price / 1e8
                    name = data[0]
                    if price > 0:
                        result[code] = {
                            "code": code,
                            "name": name,
                            "price": price,
                            "change": change,
                            "volume": volume,
                            "amount": amount,
                        }
                except (IndexError, ValueError, ZeroDivisionError):
                    continue
        return result

    def _get_hot_sectors(self) -> list[dict]:
        try:
            response = self._http_get(SINA_SECTOR_URL, headers={"Referer": "http://finance.sina.com.cn"}, timeout=15)
            response.encoding = "gbk"
            text = response.text
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return []
            payload = json.loads(text[start : end + 1])
            sectors: list[dict] = []
            for _, value in payload.items():
                parts = value.split(",")
                if len(parts) < 13:
                    continue
                try:
                    sectors.append(
                        {
                            "name": parts[1],
                            "change": float(parts[4]),
                            "count": int(parts[2]),
                            "lead": parts[12],
                        }
                    )
                except Exception:
                    continue
            sectors.sort(key=lambda row: row["change"], reverse=True)
            return sectors[:10]
        except Exception as error:
            logger.warning("Sector fetch failed error=%s", error)
            return []

    def _get_market_index(self) -> dict:
        try:
            response = self._http_get(
                f"{SINA_QUOTE_URL}sh000001,sz399001,sz399006",
                headers=SINA_QUOTE_HEADERS,
                timeout=10,
            )
        except Exception as error:
            logger.warning("Market index fetch failed error=%s", error)
            return {}

        result: dict[str, dict] = {}
        name_map = {"sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}
        for line in response.text.strip().split("\n"):
            if "var hq_str_" not in line or '=""' in line:
                continue
            try:
                symbol = line.split("_str_")[1].split("=")[0]
                data = line.split('"')[1].split(",")
                if len(data) < 4 or symbol not in name_map:
                    continue
                price = float(data[3])
                previous_close = float(data[2])
                change = (price - previous_close) / previous_close * 100 if previous_close > 0 else 0
                result[name_map[symbol]] = {"price": price, "change": change}
            except (IndexError, ValueError, ZeroDivisionError):
                continue
        return result

    def _get_kline_bars(self, symbol: str, days: int = 320) -> list[DailyBarSnapshot]:
        remote_bars = self._fetch_sina_kline_bars(symbol, days)
        if remote_bars:
            return remote_bars
        bars = self.history_service.get_daily_bars(symbol, limit=days)
        if bars:
            return bars
        return []

    def _fetch_sina_kline_bars(self, symbol: str, days: int) -> list[DailyBarSnapshot]:
        try:
            response = self._http_get(
                f"{SINA_KLINE_URL}?symbol={symbol}&scale=10080&ma=no&datalen={days}",
                headers=SINA_QUOTE_HEADERS,
                timeout=15,
            )
            payload = response.json()
        except Exception as error:
            logger.warning("Sina kline fetch failed symbol=%s error=%s", symbol, error)
            return []

        if not isinstance(payload, list) or len(payload) < 30:
            return []

        bars: list[DailyBarSnapshot] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            trade_day = str(row.get("day", "") or row.get("date", "")).strip()
            if not trade_day:
                continue
            try:
                bars.append(
                    DailyBarSnapshot(
                        symbol=symbol,
                        trade_date=date.fromisoformat(trade_day[:10]),
                        open_price=float(row.get("open", 0)),
                        close_price=float(row.get("close", 0)),
                        high_price=float(row.get("high", 0)),
                        low_price=float(row.get("low", 0)),
                        volume=float(row.get("volume", 0)),
                        turnover=None,
                        change_pct=None,
                    )
                )
            except (TypeError, ValueError):
                continue
        return bars

    def _analyze_tech(self, bars: list[DailyBarSnapshot], market_state: dict, config: dict) -> dict[str, object]:
        if len(bars) < 30:
            return {"valid": False, "score": 0, "signals": [], "dim": {}}

        closes = [float(bar.close_price) for bar in bars]
        highs = [float(bar.high_price) for bar in bars]
        lows = [float(bar.low_price) for bar in bars]
        volumes = [float(bar.volume) for bar in bars]

        ma5 = self._moving_average(closes, 5)
        ma10 = self._moving_average(closes, 10)
        ma20 = self._moving_average(closes, 20)
        ma60 = self._moving_average(closes, 60)

        dif_series = self._ema(closes, 12)
        dea_series = self._ema(dif_series, 9)
        macd_hist_series = [(dif - dea) * 2 for dif, dea in zip(dif_series, dea_series)]

        k_series, d_series = self._kdj_series(highs, lows, closes)
        boll = self._boll(closes, 20)
        rsi_series = self._rsi_series(closes, 14)
        vol_ma20 = self._rolling_mean(volumes, 20)
        returns = self._returns(closes)
        volatility20 = self._rolling_std(returns, 20)
        fund_flow_20, fund_flow_10 = self._fund_flow(closes, volumes)
        nine_turn_value, nine_turn_signal = self._nine_turn(closes)

        latest_close = closes[-1]
        latest_volume = volumes[-1]
        latest_vol_ma20 = vol_ma20[-1]
        latest_macd_hist = macd_hist_series[-1]
        previous_macd_hist = macd_hist_series[-2]
        latest_k = k_series[-1]
        latest_d = d_series[-1]
        previous_k = k_series[-2]
        previous_d = d_series[-2]
        latest_rsi = rsi_series[-1]
        latest_volatility = volatility20[-1] * math.sqrt(20) if volatility20[-1] is not None else 0.0

        signals: list[str] = []
        quality = 0.0
        trend = 0.0
        trading = 0.0
        risk = 0.0
        fund_flow_score = 0.0
        k_pattern = 0.0
        nine_turn_score = 0.0

        if latest_vol_ma20 and latest_volume > latest_vol_ma20 * 1.1:
            quality += 8
            signals.append("流动性优于20日均量")
        elif latest_vol_ma20 and latest_volume > latest_vol_ma20 * 0.8:
            quality += 4
        if latest_volatility < 0.035:
            quality += 8
            signals.append("波动率温和")
        elif latest_volatility > 0.08:
            quality -= float(config.get("scoring", {}).get("volatility_penalty", 10))
            signals.append("波动率偏高")

        if ma5 and ma10 and ma20 and ma60 and ma5 > ma10 > ma20 > ma60:
            trend += 12
            signals.append("均线多头共振")
        elif ma5 and ma10 and ma20 and ma5 > ma10 > ma20:
            trend += 8
            signals.append("中短期趋势向上")
        elif ma5 and ma10 and ma5 > ma10:
            trend += 4
            signals.append("短期趋势向上")
        if latest_macd_hist > 0:
            trend += 5
            signals.append("MACD红柱")
        if latest_macd_hist > 0 and previous_macd_hist <= 0:
            trend += 3
            signals.append("MACD金叉")
        if ma20 and latest_close > ma20:
            trend += 2
            signals.append("价格在20日均线上方")
        trend = min(20, trend)

        if fund_flow_10 > 0:
            fund_flow_score += 15
            signals.append("短期主力资金流入")
        elif fund_flow_10 < 0:
            fund_flow_score -= 10
            signals.append("短期主力资金流出")
        if fund_flow_20 > 0:
            fund_flow_score += 10
            signals.append("中期主力资金流入")
        elif fund_flow_20 < 0:
            fund_flow_score -= 5
            signals.append("中期主力资金流出")
        fund_flow_score = max(0, min(25, fund_flow_score))

        if latest_k > latest_d and previous_k <= previous_d:
            k_pattern += 8
            signals.append("KDJ金叉")
        elif latest_k > latest_d:
            k_pattern += 4
            signals.append("KDJ多头")
        if ma5 and ma10 and ma20 and ma5 > ma10 > ma20:
            k_pattern += 8
            signals.append("均线多头排列")
        elif ma5 and ma10 and ma5 > ma10:
            k_pattern += 4
            signals.append("短期均线多头")
        if boll and latest_close > boll["upper"]:
            k_pattern += 5
            signals.append("布林带上轨突破")
        elif boll and latest_close > boll["mid"]:
            k_pattern += 3
            signals.append("价格在布林带中轨上方")
        if 40 <= latest_rsi <= 65:
            k_pattern += 4
            signals.append("RSI处于可交易区间")
        k_pattern = min(25, k_pattern)

        if nine_turn_signal == -1:
            nine_turn_score += 15
            signals.append("神奇九转买入信号")
        elif nine_turn_signal == 1:
            nine_turn_score -= 10
            signals.append("神奇九转卖出信号")
        elif nine_turn_value > 0:
            nine_turn_score = nine_turn_value * 1.5
        elif nine_turn_value < 0:
            nine_turn_score = abs(nine_turn_value) * 1.5
        nine_turn_score = max(0, min(15, nine_turn_score))

        if latest_k > latest_d:
            trading += 5
        if latest_k < 25 and latest_d < 25:
            trading += 5
            signals.append("KDJ低位修复")
        if boll:
            boll_pos = (latest_close - boll["lower"]) / max(boll["upper"] - boll["lower"], 0.0001)
            if 0.15 <= boll_pos <= 0.65:
                trading += 5
                signals.append("布林位置健康")
            elif boll_pos > 0.92:
                trading -= 3
                risk -= 4
                signals.append("短线过热")
        if 35 <= latest_rsi <= 68:
            trading += 6
            signals.append("RSI处于可交易区间")
        elif latest_rsi > 78:
            risk -= 6
            signals.append("RSI过热")

        if market_state.get("regime") == "strong":
            trend += float(config.get("scoring", {}).get("market_bonus", 6))
        elif market_state.get("regime") == "weak":
            trend -= float(config.get("scoring", {}).get("market_penalty", 8)) * 0.5
            risk -= 2
        if latest_volatility < 0.03:
            risk += 6
        elif latest_volatility > 0.09:
            risk -= 8
        if ma20 and latest_close < ma20:
            risk -= 5

        score = max(0, quality + trend + trading + risk)
        dim = {
            "quality": round(max(0, quality), 1),
            "trend": round(max(0, trend), 1),
            "trading": round(max(0, trading), 1),
            "risk": round(max(0, risk), 1),
            "fund_flow": round(max(0, fund_flow_score), 1),
            "k_pattern": round(max(0, k_pattern), 1),
            "nine_turn": round(max(0, nine_turn_score), 1),
        }
        return {
            "valid": True,
            "score": round(score, 1),
            "signals": signals,
            "dim": dim,
            "ma5": self._round_or_none(ma5),
            "ma10": self._round_or_none(ma10),
            "ma20": self._round_or_none(ma20),
            "boll_lower": self._round_or_none(boll["lower"] if boll else None),
            "boll_mid": self._round_or_none(boll["mid"] if boll else None),
            "atr_proxy": round(self._atr_proxy(highs, lows), 4),
            "volatility": latest_volatility,
            "rsi": round(latest_rsi, 2),
            "latest_close": round(latest_close, 4),
            "fund_flow_10": round(fund_flow_10, 2),
            "fund_flow_20": round(fund_flow_20, 2),
            "nine_turn_signal": int(nine_turn_signal),
        }

    def _score_stock(
        self,
        spot: dict,
        tech: dict,
        lhb_signal: DragonTigerSignal,
        market_state: dict,
        sector_map: dict[str, dict],
        config: dict,
    ) -> tuple[float, list[str], dict]:
        amount = spot.get("amount", 0)
        technical_total = (
            tech["dim"].get("trend", 0)
            + tech["dim"].get("fund_flow", 0)
            + tech["dim"].get("k_pattern", 0)
            + tech["dim"].get("nine_turn", 0)
        )
        technical_total = max(0, min(80, technical_total))
        lhb_total = max(0, min(10, lhb_signal.score_delta))

        hot_sectors_score = 0.0
        hottest_sector = next(iter(sector_map.values()), None)
        if hottest_sector and hottest_sector.get("change", 0) > 2:
            hot_sectors_score = 5.0

        market_adjust = 0.0
        if market_state["regime"] == "strong":
            market_adjust += float(config.get("scoring", {}).get("market_bonus", 6))
        elif market_state["regime"] == "weak":
            market_adjust -= float(config.get("scoring", {}).get("market_penalty", 8)) * 0.5

        liquidity_adjust = float(config.get("scoring", {}).get("liquidity_bonus", 8)) if amount > float(config.get("min_volume", 1)) * 3 else 0.0
        total = max(0.0, technical_total + lhb_total + hot_sectors_score + market_adjust + liquidity_adjust)

        signals = list(tech["signals"])
        if market_adjust > 0:
            signals.append("市场环境加分")
        elif market_adjust < 0:
            signals.append("市场环境压制")
        if liquidity_adjust > 0:
            signals.append("成交额充足")
        if lhb_signal.tag == "BLACK":
            signals.append("龙虎榜黑榜回避")

        dim = {
            "technical": round(technical_total, 1),
            "lhb": round(lhb_total, 1),
            "hot_sectors": round(hot_sectors_score, 1),
            "market": round(market_adjust, 1),
            "liquidity": round(liquidity_adjust, 1),
            "trend": round(tech["dim"].get("trend", 0), 1),
            "fund_flow": round(tech["dim"].get("fund_flow", 0), 1),
            "k_pattern": round(tech["dim"].get("k_pattern", 0), 1),
            "nine_turn": round(tech["dim"].get("nine_turn", 0), 1),
        }
        return round(total, 1), signals, dim

    def _calc_trade_plan(self, price: float, tech: dict, market_state: dict, config: dict) -> dict:
        risk_cfg = config.get("risk_control", {})
        atr_proxy = max(float(tech.get("atr_proxy", 0)), price * 0.02)
        stop_loss_pct = float(risk_cfg.get("stop_loss_pct", 5)) / 100
        base_stop = max(price * (1 - stop_loss_pct), price - atr_proxy)
        support_candidates = [base_stop]
        if float(tech.get("ma20", 0) or 0) > 0:
            support_candidates.append(float(tech.get("ma20", price)))
        if float(tech.get("boll_lower", 0) or 0) > 0:
            support_candidates.append(float(tech.get("boll_lower", price)))
        support_stop = max(support_candidates)
        stop = round(max(price * 0.9, min(price * 0.97, support_stop)), 2)

        target_gain_pct = float(risk_cfg.get("target_gain_pct", 15)) / 100
        trend_adjust = 1.2 if market_state["regime"] == "strong" else (0.95 if market_state["regime"] == "weak" else 1.0)
        target_anchor = float(tech.get("boll_mid", price * 1.05) or price * 1.05)
        target = round(max(price * (1 + max(0.05, target_gain_pct * trend_adjust)), target_anchor, price * 1.05), 2)
        reward = max(target - price, 0.01)
        risk = max(price - stop, 0.01)
        risk_reward = round(reward / risk, 2)
        if market_state["regime"] == "weak":
            risk_reward = max(risk_reward, 1.0)
        return {
            "target": target,
            "stop": stop,
            "risk_reward": risk_reward,
            "invalid_condition": f"跌破{stop}或收盘持续弱于20日均线",
        }

    def _decide_timing(self, score: float, risk_reward: float, market_state: dict, config: dict) -> str:
        threshold_adjust = -4 if market_state["regime"] == "strong" else (-6 if market_state["regime"] == "weak" else 0)
        min_risk_reward = float(config.get("risk_control", {}).get("min_risk_reward", 1.0))
        min_score = float(config.get("min_score", 30))
        if market_state["regime"] == "weak":
            if score >= 50 + threshold_adjust and risk_reward >= 1.5:
                return "STRONG BUY"
            if score >= 40 + threshold_adjust and risk_reward >= 1.2:
                return "BUY"
            if score >= 20 + threshold_adjust and risk_reward >= min_risk_reward:
                return "WATCH"
        else:
            if score >= 78 + threshold_adjust and risk_reward >= 2.0:
                return "STRONG BUY"
            if score >= 66 + threshold_adjust and risk_reward >= 1.8:
                return "BUY"
            if score >= min_score + threshold_adjust - 4 and risk_reward >= min_risk_reward:
                return "WATCH"
        return "PASS"

    def _build_position_advice(self, results: list[dict], market_state: dict, config: dict) -> dict:
        risk_cfg = config.get("risk_control", {})
        if market_state["regime"] == "strong":
            total_position = risk_cfg.get("strong_market_position_pct", 65)
        elif market_state["regime"] == "weak":
            total_position = risk_cfg.get("weak_market_position_pct", 25)
        else:
            total_position = risk_cfg.get("neutral_market_position_pct", 45)
        return {
            "total_position": total_position,
            "single_position": risk_cfg.get("max_position_pct", 18),
            "strong_buy_count": sum(1 for item in results if item["timing"] == "STRONG BUY"),
            "buy_count": sum(1 for item in results if item["timing"] == "BUY"),
            "watch_count": sum(1 for item in results if item["timing"] == "WATCH"),
        }

    def _assess_market_regime(self, market: dict, hot_sectors: list[dict]) -> dict:
        changes = [data["change"] for data in market.values()]
        avg_change = sum(changes) / len(changes) if changes else 0
        top_sector = hot_sectors[0]["change"] if hot_sectors else 0
        regime = "neutral"
        if avg_change > 0.8 and top_sector > 1.5:
            regime = "strong"
        elif avg_change < -0.5:
            regime = "weak"
        description_map = {
            "strong": "风险偏好回升，顺势策略占优",
            "neutral": "市场震荡分化，强调均衡与风控",
            "weak": "风险偏好收缩，优先控制回撤",
        }
        return {
            "regime": regime,
            "avg_change": round(avg_change, 2),
            "top_sector_change": round(top_sector, 2),
            "description": description_map[regime],
        }

    def _generate_markdown_report(
        self,
        *,
        lhb: DragonTigerAnalyzer | None,
        market: dict,
        market_state: dict,
        hot_sectors: list[dict],
        pool_summary: dict,
        results: list[dict],
        excluded_by_lhb: list[dict],
        spots: dict[str, dict],
        position_advice: dict,
    ) -> str:
        lines = []
        lhb_tables = self._summarize_lhb_table(lhb)
        lines.append("# 智能选股综合系统 V8.0 专业投资决策报告")
        lines.append("")
        lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- 市场判定：{market_state['description']}")
        lines.append(f"- 候选股票数：{pool_summary.get('final_candidate_count', 0)}")
        lines.append(f"- 推荐股票数：{len(results)}")
        lines.append("")

        lines.append("## 市场环境")
        lines.append("")
        if market:
            lines.append("| 指数 | 点位 | 涨跌幅 |")
            lines.append("| --- | ---: | ---: |")
            for name, data in market.items():
                lines.append(f"| {name} | {float(data['price']):.2f} | {float(data['change']):+.2f}% |")
        else:
            lines.append("- 大盘指数数据暂不可用")
        lines.append("")
        lines.append(f"- 平均指数变动：{float(market_state.get('avg_change', 0)):.2f}%")
        lines.append(f"- 最强板块涨幅：{float(market_state.get('top_sector_change', 0)):.2f}%")
        lines.append("")

        lines.append("## 候选池概况")
        lines.append("")
        lines.append(f"- 股票池模式：{pool_summary.get('mode', '-')}")
        lines.append(f"- 机构推荐池数量：{pool_summary.get('institution_pool_count', 0)}")
        lines.append(f"- 自选池数量：{pool_summary.get('watchlist_count', 0)}")
        lines.append(f"- 最终候选数量：{pool_summary.get('final_candidate_count', 0)}")
        lines.append("")

        stats = pool_summary.get("institution_pool_stats", {})
        if stats.get("enabled"):
            lines.append("## 机构推荐动态池统计")
            lines.append("")
            lines.append(f"- 抓取页数：{stats.get('pages_fetched', 0)}")
            lines.append(f"- 总抓取条数：{stats.get('total_rows', 0)}")
            lines.append(f"- 去重后条数：{stats.get('deduped_rows', 0)}")
            lines.append(f"- 去重移除数量：{stats.get('duplicates_removed', 0)}")
            lines.append(f"- 最终动态池大小：{stats.get('final_pool_size', 0)}")
            lines.append(f"- 近端窗口：最近 {stats.get('lookback_days', 0)} 天")
            lines.append("")

        lines.append("## 龙虎榜摘要")
        lines.append("")
        if lhb:
            lines.append(f"- 黑榜席位：{len(lhb.black_seats)}")
            lines.append(f"- 红榜席位：{len(lhb.red_seats)}")
            lines.append(f"- 黑榜股票：{len(lhb.black_stocks)}")
            lines.append(f"- 红榜股票：{len(lhb.red_stocks)}")
            lines.append("")
            if lhb_tables["black_seats"]:
                lines.append("### 黑榜席位 Top")
                lines.append("")
                lines.append("| 席位 | 净买额(万) |")
                lines.append("| --- | ---: |")
                for item in lhb_tables["black_seats"]:
                    lines.append(f"| {str(item['seat'])[:40]} | {float(item['net']) / 1e4:+.0f} |")
                lines.append("")
            if lhb_tables["red_seats"]:
                lines.append("### 红榜席位 Top")
                lines.append("")
                lines.append("| 席位 | 净买额(万) |")
                lines.append("| --- | ---: |")
                for item in lhb_tables["red_seats"]:
                    lines.append(f"| {str(item['seat'])[:40]} | {float(item['net']) / 1e4:+.0f} |")
                lines.append("")
            if lhb_tables["black_stocks"]:
                lines.append("### 黑榜股票 Top")
                lines.append("")
                lines.append("| 股票 | 净买额(万) | 席位数 |")
                lines.append("| --- | ---: | ---: |")
                for item in lhb_tables["black_stocks"]:
                    lines.append(f"| {item['name']} | {float(item['net']) / 1e4:+.0f} | {item['count']} |")
                lines.append("")
            if lhb_tables["red_stocks"]:
                lines.append("### 红榜股票 Top")
                lines.append("")
                lines.append("| 股票 | 净买额(万) | 席位数 |")
                lines.append("| --- | ---: | ---: |")
                for item in lhb_tables["red_stocks"]:
                    lines.append(f"| {item['name']} | {float(item['net']) / 1e4:+.0f} | {item['count']} |")
                lines.append("")
        else:
            lines.append("- 龙虎榜数据暂不可用，策略按降级模式执行")
        lines.append("")

        lines.append("## 热门板块")
        lines.append("")
        if hot_sectors:
            lines.append("| 板块 | 涨幅 | 家数 | 领涨股 |")
            lines.append("| --- | ---: | ---: | --- |")
            for sector in hot_sectors[:10]:
                lines.append(
                    f"| {sector['name']} | {float(sector['change']):+.2f}% | {sector.get('count', 0)} | {sector.get('lead', '')} |"
                )
        else:
            lines.append("- 板块数据暂不可用")
        lines.append("")

        lines.append("## 推荐股票")
        lines.append("")
        if results:
            sorted_results = sorted(results, key=lambda row: row["score"], reverse=True)[:10]

            lines.append("| 排名 | 股票名称 | 代码 | 综合评分 | 趋势均线 | 主力资金 | K线形态 | 神奇九转 | 龙虎榜 |")
            lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
            for index, item in enumerate(sorted_results, start=1):
                dim = item.get("dim", {})
                lhb_tag = item.get("lhb_tag", "N/A")
                lhb_icon = "🟢" if lhb_tag == "RED" else "🔴" if lhb_tag == "BLACK" else "🟡"
                lines.append(
                    f"| {index} | {item['name']} | {item['code']} | {float(item['score']):.1f} | "
                    f"{float(dim.get('trend', 0)):.0f}/20 | {float(dim.get('fund_flow', 0)):.0f}/25 | "
                    f"{float(dim.get('k_pattern', 0)):.0f}/25 | {float(dim.get('nine_turn', 0)):.0f}/15 | {lhb_icon} |"
                )
            lines.append("")

            for index, item in enumerate(sorted_results, start=1):
                trend_score = float(item.get("dim", {}).get("trend", 0))
                fund_flow_score = float(item.get("dim", {}).get("fund_flow", 0))
                k_pattern_score = float(item.get("dim", {}).get("k_pattern", 0))
                nine_turn_score = float(item.get("dim", {}).get("nine_turn", 0))
                lhb_tag = item.get("lhb_tag", "N/A")
                lhb_detail = item.get("lhb_detail", {})
                sectors = item.get("hot_sectors", [])
                strong_count = 0
                strong_count += int(trend_score >= 15)
                strong_count += int(fund_flow_score >= 20)
                strong_count += int(k_pattern_score >= 20)
                strong_count += int(nine_turn_score >= 12)

                lines.append(f"### {index}. {item['name']} ({item['code']}) {self._score_to_stars(float(item['score']))}")
                lines.append("")
                lines.append("**基础信息**")
                lines.append(f"- 当前价格：{float(item['price']):.2f} 元")
                lines.append(f"- 日涨幅：{float(item['change']):+.2f}%{'（涨停）' if float(item['change']) >= 9.9 else ''}")
                lines.append(f"- 成交额：{float(item.get('amount', 0)):.2f} 亿元")
                lines.append(f"- 综合评分：{float(item['score']):.1f} 分")
                lines.append("")

                if lhb_tag == "RED":
                    lines.append("**龙虎榜 🟢**")
                    lines.append(f"- 净买入：{float(lhb_detail.get('red_net', 0)) / 1e8:.2f} 亿元")
                    lines.append("- 评级：🟢 红榜")
                elif lhb_tag == "BLACK":
                    lines.append("**龙虎榜 🔴**")
                    lines.append(f"- 净买入：{-float(lhb_detail.get('black_net', 0)) / 1e8:.2f} 亿元")
                    lines.append("- 评级：🔴 黑榜")
                else:
                    lines.append("**龙虎榜 🟡**")
                    lines.append("- 评级：🟡 中性")
                lines.append("")

                lines.append("**热门板块 🔥**")
                if sectors:
                    for sector in sectors[:3]:
                        lines.append(f"- {sector}")
                else:
                    lines.append("- 暂无热门板块信息")
                lines.append("")

                lines.append("**四大指标评分**")
                lines.append(f"- 趋势均线：{trend_score:.0f}/20 ⭐")
                if trend_score >= 15:
                    lines.append("  - ✅ 金叉确认")
                    lines.append("  - ✅ 多头排列")
                lines.append("")
                lines.append(f"- 主力资金：{fund_flow_score:.0f}/25 ⭐")
                if fund_flow_score >= 20:
                    lines.append("  - ✅ 吸筹阶段")
                    lines.append("  - ✅ 游资集中进场")
                lines.append("")
                lines.append(f"- K线形态：{k_pattern_score:.0f}/25 ⭐")
                if k_pattern_score >= 20:
                    lines.append("  - ✅ 放量涨停突破")
                    lines.append("  - ✅ 底部反转形态")
                lines.append("")
                lines.append(f"- 神奇九转：{nine_turn_score:.0f}/15")
                if nine_turn_score >= 12:
                    lines.append("  - ✅ 连跌后反弹")
                lines.append("")

                lines.append("**总结**")
                if lhb_tag == "RED":
                    lines.append("- 龙虎榜：🟢 红榜")
                elif lhb_tag == "BLACK":
                    lines.append("- 龙虎榜：🔴 黑榜")
                else:
                    lines.append("- 龙虎榜：🟡 中性")
                if sectors:
                    lines.append(f"- 热门板块：🔥 {sectors[0]}")
                lines.append(
                    f"- 四大指标：{'✅' * strong_count}{'❌' * (4 - strong_count)} 全优"
                    if strong_count == 4
                    else f"- 四大指标：{'✅' * strong_count}{'❌' * (4 - strong_count)}"
                )
                if strong_count >= 3 and lhb_tag == "RED":
                    lines.append("→ 推荐关注")
                elif strong_count >= 2:
                    lines.append("→ 可适当关注")
                else:
                    lines.append("→ 建议观察")
                lines.append("")
        else:
            lines.append("- 当前无符合专业风控要求的推荐标的")
            lines.append("")

        lines.append("## 黑榜排除")
        lines.append("")
        if excluded_by_lhb:
            for item in excluded_by_lhb:
                lines.append(f"- {item['name']} ({item['code']})：{item['reason']}")
        else:
            lines.append("- 无黑榜排除项")
        lines.append("")

        lines.append("## 仓位建议")
        lines.append("")
        lines.append(f"- 总仓位上限：{position_advice['total_position']}%")
        lines.append(f"- 单标的仓位上限：{position_advice['single_position']}%")
        lines.append(f"- 强烈买入：{position_advice['strong_buy_count']} 只")
        lines.append(f"- 买入：{position_advice['buy_count']} 只")
        lines.append(f"- 观察：{position_advice['watch_count']} 只")
        lines.append("")

        lines.append("## 数据源声明")
        lines.append("")
        lines.append(f"- 实时行情候选：{len(spots)} 只")
        lines.append("- K线数据：新浪财经 API")
        lines.append("- 板块数据：新浪财经行业板块")
        lines.append("- 龙虎榜：AKShare stock_lhb_hyyyb_em")
        lines.append("")

        institution_rows = pool_summary.get("institution_pool_rows", [])
        if institution_rows:
            latest_date = institution_rows[0].get("rating_date", "")
            lines.append(f"## 机构推荐动态池明细（{latest_date}）" if latest_date else "## 机构推荐动态池明细")
            lines.append("")
            lines.append("| 代码 | 名称 | 推荐次数 | 机构 | 行业 | 目标价 | 最新价 | 涨跌幅 | 目标涨幅 |")
            lines.append("| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: |")
            for row in institution_rows:
                target_price = row.get("target_price") or "-"
                latest_price = row.get("latest_price") or "-"
                change_pct = row.get("change_pct") or "-"
                recommend_count = row.get("recommend_count", 1)
                institutions = self._markdown_multiline_cell(row.get("institutions", []))
                industries = self._markdown_multiline_cell(row.get("industries", []))
                stock_url = self._build_sina_stock_url(str(row["code"]))
                target_gain = self._compute_target_gain(target_price, latest_price)
                lines.append(
                    f"| {row['code']} | [{row['name']}]({stock_url}) | {recommend_count} | {institutions} | "
                    f"{industries} | {target_price} | {latest_price} | {change_pct} | {target_gain} |"
                )
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _score_to_stars(score: float) -> str:
        if score >= 95:
            return "⭐⭐⭐⭐⭐"
        if score >= 90:
            return "⭐⭐⭐⭐"
        if score >= 85:
            return "⭐⭐⭐"
        if score >= 80:
            return "⭐⭐"
        return "⭐"

    def _build_sina_stock_url(self, code: str) -> str:
        symbol = self._normalize_symbol(code)
        if not symbol:
            return "https://finance.sina.com.cn"
        return f"https://finance.sina.com.cn/realstock/company/{symbol}/nc.shtml"

    @staticmethod
    def _markdown_multiline_cell(values: object) -> str:
        if isinstance(values, list):
            normalized = [str(item).strip() for item in values if str(item).strip()]
        elif values:
            normalized = [str(values).strip()]
        else:
            normalized = []

        unique_values = list(dict.fromkeys(normalized))
        if not unique_values:
            return "-"
        return "<br>".join(f"- {item}" for item in unique_values)

    @staticmethod
    def _compute_target_gain(target_price: object, latest_price: object) -> str:
        if target_price in (None, "-", "") or latest_price in (None, "-", ""):
            return "-"
        try:
            target_value = float(str(target_price).replace(",", ""))
            latest_value = float(str(latest_price).replace(",", ""))
        except (TypeError, ValueError):
            return "-"
        if latest_value <= 0:
            return "-"
        gain = ((target_value - latest_value) / latest_value) * 100
        return f"{gain:+.2f}%"

    @staticmethod
    def _summarize_lhb_table(lhb: DragonTigerAnalyzer | None, limit: int = 8) -> dict[str, list[dict]]:
        if lhb is None:
            return {"black_seats": [], "red_seats": [], "black_stocks": [], "red_stocks": []}

        black_stock_rows: list[dict] = []
        for stock_name, entries in lhb.black_stocks.items():
            total_net = sum(float(item["net"]) for item in entries)
            black_stock_rows.append({"name": stock_name, "net": total_net, "count": len(entries)})

        red_stock_rows: list[dict] = []
        for stock_name, entries in lhb.red_stocks.items():
            total_net = sum(float(item["net"]) for item in entries)
            red_stock_rows.append({"name": stock_name, "net": total_net, "count": len(entries)})

        black_stock_rows.sort(key=lambda item: abs(item["net"]), reverse=True)
        red_stock_rows.sort(key=lambda item: abs(item["net"]), reverse=True)
        black_seat_rows = sorted(lhb.black_seats, key=lambda item: abs(float(item["net"])), reverse=True)[:limit]
        red_seat_rows = sorted(lhb.red_seats, key=lambda item: abs(float(item["net"])), reverse=True)[:limit]

        return {
            "black_seats": black_seat_rows,
            "red_seats": red_seat_rows,
            "black_stocks": black_stock_rows[:limit],
            "red_stocks": red_stock_rows[:limit],
        }

    def _build_summary(self, market_state: dict, results: list[dict], pool_summary: dict) -> str:
        if not results:
            return f"{market_state['description']}，候选池 {pool_summary.get('final_candidate_count', 0)} 只，暂无通过风控阈值的标的。"
        top = results[0]
        return (
            f"{market_state['description']}，候选池 {pool_summary.get('final_candidate_count', 0)} 只，"
            f"推荐 {len(results)} 只；首位 {top['name']}（{top['code']}）评分 {top['score']:.1f}。"
        )

    def _list_watchlist_codes(self, db: Session, tenant_id: str) -> list[str]:
        rows = db.scalars(
            select(WatchlistItem.symbol)
            .where(WatchlistItem.tenant_id == tenant_id)
            .order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
        ).all()
        codes: list[str] = []
        for symbol in rows:
            normalized = self._normalize_symbol(str(symbol))
            if normalized:
                codes.append(normalized[2:])
        return codes

    def _extract_rating_rows(
        self,
        raw_html: str,
        page_url: str,
        allowed_ratings: set[str],
        require_target_price: bool,
    ) -> list[dict]:
        text = re.sub(r"<[^>]+>", "\n", raw_html).replace("\r", "\n")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        rows: list[dict] = []
        index = 0

        def is_main_board_code(code: str) -> bool:
            return code.startswith(("000", "001", "002", "003", "300", "600", "601", "603", "605", "688"))

        while index < len(lines):
            if not re.fullmatch(r"\d{6}", lines[index]):
                index += 1
                continue
            code = lines[index]
            if not is_main_board_code(code):
                index += 1
                continue
            cursor = index + 1
            block: list[str] = []
            while cursor < len(lines) and not re.fullmatch(r"\d{6}", lines[cursor]):
                block.append(lines[cursor])
                cursor += 1

            date_pos = next((i for i, item in enumerate(block) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", item)), -1)
            if date_pos < 0 or len(block) < 5:
                index = cursor
                continue

            name = block[0]
            rating_idx = next((i for i, item in enumerate(block[:date_pos]) if item in allowed_ratings or item == "中性"), -1)
            if rating_idx <= 0:
                index = cursor
                continue

            target_price = ""
            for item in block[1:rating_idx]:
                if re.fullmatch(r"\d+(?:\.\d+)?", item):
                    target_price = item
                    break
            rating = block[rating_idx]
            if rating not in allowed_ratings:
                index = cursor
                continue
            if require_target_price and not target_price:
                index = cursor
                continue

            meta = block[rating_idx + 1 : date_pos]
            if not meta:
                index = cursor
                continue
            institution = meta[0]
            analyst = meta[1] if len(meta) > 1 else ""
            industry = meta[2] if len(meta) > 2 else ""
            rating_date = block[date_pos]
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "target_price": target_price,
                    "rating": rating,
                    "institution": institution,
                    "analyst": analyst,
                    "industry": industry,
                    "rating_date": rating_date,
                    "summary": block[date_pos + 1] if date_pos + 1 < len(block) else "摘要",
                    "latest_price": "",
                    "change_pct": "",
                    "recommend_count": 1,
                    "institutions": [institution],
                    "source_link": page_url,
                }
            )
            index = cursor
        return rows

    def _get_latest_run(self, db: Session, tenant_id: str) -> SmartSelectionRun | None:
        return db.scalar(
            select(SmartSelectionRun)
            .where(SmartSelectionRun.tenant_id == tenant_id)
            .order_by(desc(SmartSelectionRun.started_at), desc(SmartSelectionRun.id))
            .limit(1)
        )

    def _get_latest_successful_run(self, db: Session, tenant_id: str) -> SmartSelectionRun | None:
        return db.scalar(
            select(SmartSelectionRun)
            .where(
                SmartSelectionRun.tenant_id == tenant_id,
                SmartSelectionRun.status == SmartSelectionRunStatus.SUCCEEDED,
            )
            .order_by(desc(SmartSelectionRun.generated_at), desc(SmartSelectionRun.id))
            .limit(1)
        )

    def _ensure_config(self, db: Session, tenant_id: str) -> SmartSelectionConfig:
        config = db.scalar(select(SmartSelectionConfig).where(SmartSelectionConfig.tenant_id == tenant_id))
        if config is not None:
            normalized_payload = self._normalize_config_payload(config.config_payload or self._default_config())
            if normalized_payload != (config.config_payload or {}):
                config.config_payload = normalized_payload
                db.add(config)
                db.commit()
                db.refresh(config)
            return config

        config = SmartSelectionConfig(
            tenant_id=tenant_id,
            enabled=True,
            schedule_time="20:00",
            config_payload=self._default_config(),
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        return config

    @staticmethod
    @lru_cache(maxsize=1)
    def _default_config() -> dict:
        if DEFAULT_CONFIG_PATH.exists():
            try:
                return SmartSelectionService._normalize_config_payload(
                    json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
                )
            except Exception as error:
                logger.warning("Smart selection default config load failed error=%s", error)
        return {
            "lhb_keywords": {"black": ["拉萨"], "white": ["江苏路"]},
            "min_score": 30,
            "max_recommendations": 10,
            "min_volume": 1,
            "price_range": [3, 500],
            "candidate_pool": {"mode": "institution_watchlist", "batch_size": 50},
            "institution_rating_pool": {"enabled": False},
            "risk_control": {
                "stop_loss_pct": 5,
                "target_gain_pct": 15,
                "max_position_pct": 18,
                "min_risk_reward": 1.0,
                "weak_market_position_pct": 25,
                "neutral_market_position_pct": 45,
                "strong_market_position_pct": 65,
            },
            "scoring": {
                "market_bonus": 6,
                "market_penalty": 8,
                "heat_bonus": 6,
                "liquidity_bonus": 8,
                "volatility_penalty": 10,
                "lhb_red_bonus": 10,
                "lhb_black_penalty": 100,
            },
        }

    @staticmethod
    def _normalize_config_payload(payload: dict | None) -> dict:
        normalized = deepcopy(payload or {})
        candidate_pool = normalized.setdefault("candidate_pool", {})
        candidate_pool["mode"] = "institution_watchlist"
        candidate_pool["watchlist_source"] = "user_watchlist"
        candidate_pool.pop("watchlist_codes", None)
        candidate_pool.pop("fallback_codes", None)
        return normalized

    @staticmethod
    def _serialize_config(config: SmartSelectionConfig) -> SmartSelectionConfigRead:
        return SmartSelectionConfigRead(
            id=config.id,
            tenant_id=config.tenant_id,
            enabled=config.enabled,
            schedule_time=config.schedule_time,
            config_payload=config.config_payload or {},
            updated_at=config.updated_at.isoformat(),
        )

    @staticmethod
    def _serialize_run(run: SmartSelectionRun) -> SmartSelectionRunRead:
        return SmartSelectionRunRead(
            id=run.id,
            task_id=run.task_id,
            status=run.status.value,
            triggered_by=run.triggered_by,
            candidate_pool_size=run.candidate_pool_size,
            recommendation_count=run.recommendation_count,
            summary=run.summary,
            report_body=run.report_body,
            error_message=run.error_message,
            generated_at=run.generated_at.isoformat() if run.generated_at else None,
            started_at=run.started_at.isoformat(),
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
        )

    @staticmethod
    def _serialize_item(item: SmartSelectionItem) -> SmartSelectionItemRead:
        return SmartSelectionItemRead(
            symbol=item.symbol,
            code=item.code,
            name=item.name,
            score=round(item.score, 2),
            price=item.price,
            change_pct=item.change_pct,
            target_price=item.target_price,
            stop_loss_price=item.stop_loss_price,
            tags=[str(tag) for tag in (item.tags or [])],
            reason=item.reason,
            dimension_scores=item.dimension_scores or {},
            raw_detail=item.raw_detail or {},
        )

    @staticmethod
    def _build_item_tags(result: dict) -> list[str]:
        tags = [result["timing"].lower().replace(" ", "_")]
        if result.get("lhb_tag") and result["lhb_tag"] != "N/A":
            tags.append(str(result["lhb_tag"]).lower())
        tags.extend(result.get("hot_sectors", [])[:3])
        return list(dict.fromkeys(tags))

    @staticmethod
    def _http_get(url: str, *, headers: dict[str, str] | None = None, timeout: float = 10.0) -> httpx.Response:
        with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response

    @staticmethod
    def _normalize_symbol(value: str) -> str | None:
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized.startswith(("sh", "sz", "bj")) and len(normalized) >= 8:
            return normalized
        if re.fullmatch(r"\d{6}", normalized):
            if normalized.startswith(("6", "9")):
                return f"sh{normalized}"
            if normalized.startswith(("8", "4")):
                return f"bj{normalized}"
            return f"sz{normalized}"
        return None

    @staticmethod
    def _safe_float(value: object, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return default
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _moving_average(values: list[float], period: int) -> float | None:
        if len(values) < period:
            return None
        return mean(values[-period:])

    @staticmethod
    def _ema(values: list[float], period: int) -> list[float]:
        alpha = 2 / (period + 1)
        result: list[float] = []
        current: float | None = None
        for value in values:
            current = value if current is None else current + alpha * (value - current)
            result.append(current)
        return result

    @staticmethod
    def _rolling_mean(values: list[float], period: int) -> list[float | None]:
        result: list[float | None] = []
        for index in range(len(values)):
            if index + 1 < period:
                result.append(None)
            else:
                result.append(mean(values[index - period + 1 : index + 1]))
        return result

    @staticmethod
    def _rolling_std(values: list[float], period: int) -> list[float | None]:
        result: list[float | None] = []
        for index in range(len(values)):
            if index + 1 < period:
                result.append(None)
            else:
                window = values[index - period + 1 : index + 1]
                result.append(pstdev(window))
        return result

    @staticmethod
    def _returns(closes: list[float]) -> list[float]:
        result: list[float] = [0.0]
        for index in range(1, len(closes)):
            previous = closes[index - 1]
            result.append((closes[index] - previous) / previous if previous else 0.0)
        return result

    @staticmethod
    def _fund_flow(closes: list[float], volumes: list[float]) -> tuple[float, float]:
        price_changes = [0.0]
        for index in range(1, len(closes)):
            price_changes.append(closes[index] - closes[index - 1])
        money_flow_dir = [change * volume * close for change, volume, close in zip(price_changes, volumes, closes)]
        fund_flow_20 = sum(money_flow_dir[-20:]) if len(money_flow_dir) >= 20 else sum(money_flow_dir)
        fund_flow_10 = sum(money_flow_dir[-10:]) if len(money_flow_dir) >= 10 else sum(money_flow_dir)
        return fund_flow_20, fund_flow_10

    @staticmethod
    def _kdj_series(highs: list[float], lows: list[float], closes: list[float]) -> tuple[list[float], list[float]]:
        k_values: list[float] = []
        d_values: list[float] = []
        previous_k = 50.0
        previous_d = 50.0
        for index in range(len(closes)):
            start = max(0, index - 13)
            lowest = min(lows[start : index + 1])
            highest = max(highs[start : index + 1])
            rsv = 50.0 if math.isclose(highest, lowest) else (closes[index] - lowest) / (highest - lowest + 0.0001) * 100
            current_k = previous_k * 2 / 3 + rsv / 3
            current_d = previous_d * 2 / 3 + current_k / 3
            k_values.append(current_k)
            d_values.append(current_d)
            previous_k = current_k
            previous_d = current_d
        return k_values, d_values

    @staticmethod
    def _boll(closes: list[float], period: int) -> dict[str, float] | None:
        if len(closes) < period:
            return None
        window = closes[-period:]
        mid = mean(window)
        stddev = pstdev(window)
        upper = mid + 2 * stddev
        lower = mid - 2 * stddev
        return {"mid": mid, "upper": upper, "lower": lower, "width_ratio": (upper - lower) / mid if mid else 0.0}

    @staticmethod
    def _rsi_series(closes: list[float], period: int) -> list[float]:
        values: list[float] = []
        for index in range(len(closes)):
            if index == 0:
                values.append(50.0)
                continue
            start = max(1, index - period + 1)
            gains: list[float] = []
            losses: list[float] = []
            for cursor in range(start, index + 1):
                delta = closes[cursor] - closes[cursor - 1]
                gains.append(max(delta, 0.0))
                losses.append(abs(min(delta, 0.0)))
            average_gain = mean(gains) if gains else 0.0
            average_loss = mean(losses) if losses else 0.0
            if average_loss == 0:
                values.append(100.0 if average_gain > 0 else 50.0)
                continue
            rs = average_gain / average_loss
            values.append(100 - (100 / (1 + rs)))
        return values

    @staticmethod
    def _nine_turn(closes: list[float]) -> tuple[int, int]:
        if len(closes) < 10:
            return 0, 0
        index = len(closes) - 1
        up_count = 0
        for offset in range(1, 10):
            if closes[index - offset] < closes[index - offset + 1]:
                up_count += 1
            else:
                break
        if up_count == 9:
            return 9, 1
        down_count = 0
        for offset in range(1, 10):
            if closes[index - offset] > closes[index - offset + 1]:
                down_count += 1
            else:
                break
        if down_count == 9:
            return -9, -1
        return 0, 0

    @staticmethod
    def _atr_proxy(highs: list[float], lows: list[float]) -> float:
        window = [high - low for high, low in zip(highs[-14:], lows[-14:])]
        return mean(window) if window else 0.0

    @staticmethod
    def _round_or_none(value: float | None) -> float | None:
        return round(value, 4) if value is not None else None
