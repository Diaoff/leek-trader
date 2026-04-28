from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.market.providers.base import (
    MarketBreadthBucketSnapshot,
    MarketBreadthDistributionSnapshot,
    MarketFundFlowItemSnapshot,
    MarketFundFlowSnapshot,
    MarketOverviewProvider,
    MarketOverviewSnapshot,
    MarketRegionFundFlowItemSnapshot,
    MarketSymbolSnapshot,
    MarketTurnoverSnapshot,
)

logger = logging.getLogger(__name__)


class EastMoneyOverviewProvider(MarketOverviewProvider):
    name = "eastmoney"
    index_endpoint = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    ranking_endpoint = "https://push2.eastmoney.com/api/qt/clist/get"
    northbound_endpoint = "https://push2.eastmoney.com/api/qt/kamt/get"
    fund_flow_endpoint = "https://data.eastmoney.com/dataapi/bkzj/getbkzj"

    index_targets: list[tuple[str, str]] = [
        ("上证指数", "1.000001"),
        ("深证成指", "0.399001"),
        ("创业板指", "0.399006"),
    ]
    market_scope = "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23"
    ranking_page_size = 200
    ranking_page_retry_limit = 2
    st_limit_pct = 5.0
    main_board_limit_pct = 10.0
    growth_board_limit_pct = 20.0
    beijing_board_limit_pct = 30.0
    limit_buffer_pct = 0.2
    max_limit_scan_pages = 20
    excluded_fund_flow_keywords = (
        "深成",
        "昨日涨停",
        "沪股通",
        "MSCI中国",
        "央国企改革",
        "标准普尔",
        "创业板综",
        "富时罗素",
        "深股通",
        "融资融券",
        "S300",
        "沪深",
    )
    region_coordinates: dict[str, tuple[float, float]] = {
        "北京": (116.405285, 39.904989),
        "天津": (117.190182, 39.125596),
        "河北": (114.502461, 38.045474),
        "山西": (112.549248, 37.857014),
        "内蒙古": (111.670801, 40.818311),
        "辽宁": (123.429096, 41.796767),
        "吉林": (125.3245, 43.886841),
        "黑龙江": (126.642464, 45.756967),
        "上海": (121.472644, 31.231706),
        "江苏": (118.767413, 32.041544),
        "浙江": (119.5313, 29.8773),
        "安徽": (117.283042, 31.86119),
        "福建": (119.306239, 26.075302),
        "江西": (115.892151, 28.676493),
        "山东": (117.000923, 36.675807),
        "河南": (113.665412, 34.757975),
        "湖北": (114.298572, 30.584355),
        "湖南": (112.982279, 28.19409),
        "广东": (113.280637, 23.125178),
        "广西": (108.320004, 22.82402),
        "海南": (110.33119, 20.031971),
        "重庆": (106.504962, 29.533155),
        "四川": (104.065735, 30.659462),
        "贵州": (106.713478, 26.578343),
        "云南": (102.712251, 25.040609),
        "西藏": (91.132212, 29.660361),
        "陕西": (108.948024, 34.263161),
        "甘肃": (103.823557, 36.058039),
        "青海": (101.778916, 36.623178),
        "宁夏": (106.278179, 38.46637),
        "新疆": (87.617733, 43.792818),
        "台湾": (121.509062, 25.044332),
    }

    def fetch_overview(self) -> MarketOverviewSnapshot:
        indices = self._safe_fetch_indices()
        top_gainers = self._safe_fetch_ranked(fid="f3", descending=True, limit=8)
        top_losers = self._safe_fetch_ranked(fid="f3", descending=False, limit=8)
        hot_stocks = self._safe_fetch_ranked(fid="f6", descending=True, limit=8)
        northbound_net_inflow = self._safe_fetch_northbound()
        limit_up_total, limit_up_sample = self._safe_collect_limit_moves(direction="up")
        limit_down_total, limit_down_sample = self._safe_collect_limit_moves(direction="down")
        fund_flow = self._safe_fetch_fund_flow()

        return MarketOverviewSnapshot(
            generated_at=datetime.now(UTC),
            source=self.name,
            indices=indices,
            top_gainers=top_gainers,
            top_losers=top_losers,
            limit_up_total=limit_up_total,
            limit_up_sample=limit_up_sample,
            limit_down_total=limit_down_total,
            limit_down_sample=limit_down_sample,
            northbound_net_inflow=northbound_net_inflow,
            hot_stocks=hot_stocks,
            breadth_distribution=None,
            turnover=None,
            fund_flow=fund_flow,
        )

    def _safe_fetch_fund_flow(self) -> MarketFundFlowSnapshot | None:
        try:
            return self._fetch_fund_flow()
        except Exception as error:
            logger.warning("EastMoney fund flow request failed: %s", error)
            return None

    def _fetch_fund_flow(self) -> MarketFundFlowSnapshot:
        with httpx.Client(timeout=8.0, headers={"Referer": "https://data.eastmoney.com/", "User-Agent": "Mozilla/5.0"}) as client:
            regions_payload = self._fetch_fund_flow_payload(client, "m:90+t:1")
            concepts_payload = self._fetch_fund_flow_payload(client, "m:90+t:3")
            industries_payload = self._fetch_fund_flow_payload(client, "m:90+t:2")

        regions = self._parse_region_fund_flow(regions_payload)
        concepts = self._parse_fund_flow_items(concepts_payload)
        industries = self._parse_fund_flow_items(industries_payload)
        return MarketFundFlowSnapshot(
            source=self.name,
            regions=regions[:12],
            concept_top=concepts[:10],
            concept_bottom=list(reversed(concepts[-6:])),
            industry_top=industries[:10],
        )

    def _fetch_fund_flow_payload(self, client: httpx.Client, code: str) -> dict[str, Any]:
        response = client.get(self.fund_flow_endpoint, params={"key": "f174", "code": code})
        response.raise_for_status()
        return response.json()

    def _parse_region_fund_flow(self, payload: dict[str, Any]) -> list[MarketRegionFundFlowItemSnapshot]:
        result: list[MarketRegionFundFlowItemSnapshot] = []
        for rank, item in enumerate(self._sorted_fund_flow_payload(payload), start=1):
            name = self._fund_flow_name(item)
            region_name = name.removesuffix("板块")
            longitude, latitude = self.region_coordinates.get(region_name, (None, None))
            result.append(
                MarketRegionFundFlowItemSnapshot(
                    name=name,
                    net_inflow=self._fund_flow_value(item),
                    rank=rank,
                    longitude=longitude,
                    latitude=latitude,
                )
            )
        return result

    def _parse_fund_flow_items(self, payload: dict[str, Any]) -> list[MarketFundFlowItemSnapshot]:
        parsed: list[MarketFundFlowItemSnapshot] = []
        for item in self._sorted_fund_flow_payload(payload):
            name = self._fund_flow_name(item)
            if any(keyword in name for keyword in self.excluded_fund_flow_keywords):
                continue
            parsed.append(MarketFundFlowItemSnapshot(name=name, net_inflow=self._fund_flow_value(item), rank=len(parsed) + 1))
        return parsed

    def _sorted_fund_flow_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = payload.get("data", {}).get("diff", [])
        if not isinstance(rows, list):
            return []
        parsed = [row for row in rows if isinstance(row, dict)]
        return sorted(parsed, key=self._fund_flow_value, reverse=True)

    @staticmethod
    def _fund_flow_name(item: dict[str, Any]) -> str:
        return str(item.get("f14") or "未知")

    @staticmethod
    def _fund_flow_value(item: dict[str, Any]) -> float:
        try:
            return round(float(item.get("f174") or 0) / 100000000, 2)
        except (TypeError, ValueError):
            return 0.0

    def _safe_fetch_indices(self) -> list[MarketSymbolSnapshot]:
        for attempt in range(self.ranking_page_retry_limit + 1):
            try:
                return self._fetch_indices()
            except Exception as error:
                if attempt >= self.ranking_page_retry_limit:
                    logger.warning("EastMoney overview indices request failed: %s", error)
                    return []
        return []

    def _safe_fetch_ranked(self, *, fid: str, descending: bool, limit: int) -> list[MarketSymbolSnapshot]:
        for attempt in range(self.ranking_page_retry_limit + 1):
            try:
                return self._fetch_ranked_page(fid=fid, descending=descending, limit=limit, page=1)[0]
            except Exception as error:
                if attempt >= self.ranking_page_retry_limit:
                    logger.warning(
                        "EastMoney overview ranked request failed fid=%s descending=%s limit=%s error=%s",
                        fid,
                        descending,
                        limit,
                        error,
                    )
                    return []
        return []

    def _safe_fetch_ranked_all(self, *, fid: str, descending: bool, limit: int) -> list[MarketSymbolSnapshot]:
        try:
            return self._fetch_ranked_all(fid=fid, descending=descending, limit=limit)
        except Exception as error:
            logger.warning(
                "EastMoney overview ranked pagination failed fid=%s descending=%s limit=%s error=%s",
                fid,
                descending,
                limit,
                error,
            )
            return []

    def _safe_fetch_northbound(self) -> float | None:
        for attempt in range(self.ranking_page_retry_limit + 1):
            try:
                return self._fetch_northbound()
            except Exception as error:
                if attempt >= self.ranking_page_retry_limit:
                    logger.warning("EastMoney overview northbound request failed: %s", error)
                    return None
        return None

    def _safe_collect_limit_moves(self, *, direction: str) -> tuple[int, list[MarketSymbolSnapshot]]:
        descending = direction == "up"
        detector = self._is_limit_up if direction == "up" else self._is_limit_down
        total = 0
        sample: list[MarketSymbolSnapshot] = []

        try:
            for page in range(1, self.max_limit_scan_pages + 1):
                rows, _ = self._fetch_ranked_page(
                    fid="f3",
                    descending=descending,
                    limit=self.ranking_page_size,
                    page=page,
                )
                if not rows:
                    break

                for item in rows:
                    if not detector(item):
                        continue
                    total += 1
                    if len(sample) < 5:
                        sample.append(item)

                if self._reached_limit_scan_floor(rows, direction=direction):
                    break
        except Exception as error:
            logger.warning(
                "EastMoney overview limit scan interrupted direction=%s collected_total=%s sample_size=%s error=%s",
                direction,
                total,
                len(sample),
                error,
            )

        return total, sample

    def _build_breadth_distribution(
        self,
        rows: list[MarketSymbolSnapshot],
    ) -> MarketBreadthDistributionSnapshot | None:
        if not rows:
            return None

        bucket_specs = [
            ("gt_10", ">10%", lambda value: value > 10.0, "rise"),
            ("up_7_10", "7~10%", lambda value: 7.0 < value <= 10.0, "rise"),
            ("up_5_7", "5~7%", lambda value: 5.0 < value <= 7.0, "rise"),
            ("up_3_5", "3~5%", lambda value: 3.0 < value <= 5.0, "rise"),
            ("up_0_3", "0~3%", lambda value: 0.0 < value <= 3.0, "rise"),
            ("down_0_3", "0~-3%", lambda value: -3.0 <= value < 0.0, "fall"),
            ("down_3_5", "-3~-5%", lambda value: -5.0 <= value < -3.0, "fall"),
            ("down_5_7", "-5~-7%", lambda value: -7.0 <= value < -5.0, "fall"),
            ("down_7_10", "-7~-10%", lambda value: -10.0 <= value < -7.0, "fall"),
            ("lt_10", "<-10%", lambda value: value < -10.0, "fall"),
        ]

        buckets: list[MarketBreadthBucketSnapshot] = []
        values = [row.change_percent for row in rows if row.change_percent is not None]
        if not values:
            return None

        advancing_count = sum(value > 0 for value in values)
        declining_count = sum(value < 0 for value in values)
        flat_count = max(len(values) - advancing_count - declining_count, 0)

        for key, label, matcher, tone in bucket_specs:
            buckets.append(
                MarketBreadthBucketSnapshot(
                    key=key,
                    label=label,
                    count=sum(1 for value in values if matcher(value)),
                    tone=tone,
                )
            )

        return MarketBreadthDistributionSnapshot(
            advancing_count=advancing_count,
            flat_count=flat_count,
            declining_count=declining_count,
            buckets=buckets,
            source=self.name,
        )

    def _build_turnover_snapshot(self, rows: list[MarketSymbolSnapshot]) -> MarketTurnoverSnapshot | None:
        amounts = [row.volume for row in rows if row.volume > 0]
        if not amounts:
            return None

        today_amount = round(sum(amounts), 2)
        estimated_full_day_amount = round(today_amount / self._trading_progress_ratio(), 2) if today_amount > 0 else None
        return MarketTurnoverSnapshot(
            today_amount=today_amount,
            previous_day_amount=None,
            delta_amount=None,
            estimated_full_day_amount=estimated_full_day_amount,
            source=self.name,
        )

    def _is_limit_up(self, item: MarketSymbolSnapshot) -> bool:
        threshold = self._limit_threshold_pct(item)
        if threshold is None or item.change_percent is None:
            return False
        return item.change_percent >= (threshold - self.limit_buffer_pct)

    def _is_limit_down(self, item: MarketSymbolSnapshot) -> bool:
        threshold = self._limit_threshold_pct(item)
        if threshold is None or item.change_percent is None:
            return False
        return item.change_percent <= -(threshold - self.limit_buffer_pct)

    def _limit_threshold_pct(self, item: MarketSymbolSnapshot) -> float | None:
        symbol = item.symbol.lower()
        code = item.code
        name = item.name.upper()

        if "ST" in name:
            return self.st_limit_pct
        if symbol.startswith("bj") or code.startswith(("4", "8")):
            return self.beijing_board_limit_pct
        if code.startswith(("300", "301", "688", "689")):
            return self.growth_board_limit_pct
        return self.main_board_limit_pct

    def _reached_limit_scan_floor(self, rows: list[MarketSymbolSnapshot], *, direction: str) -> bool:
        if not rows:
            return True

        floor = self.st_limit_pct - self.limit_buffer_pct
        boundary = rows[-1].change_percent
        if boundary is None:
            return False
        if direction == "up":
            return boundary < floor
        return boundary > -floor

    def _fetch_indices(self) -> list[MarketSymbolSnapshot]:
        payload = self._get_json(
            self.index_endpoint,
            params={
                "secids": ",".join(secid for _, secid in self.index_targets),
                "fields": "f12,f14,f2,f3,f6,f13,f100",
            },
        )
        return self._parse_rows(payload)

    def _fetch_ranked_all(self, *, fid: str, descending: bool, limit: int) -> list[MarketSymbolSnapshot]:
        rows: list[MarketSymbolSnapshot] = []
        seen_symbols: set[str] = set()
        target = max(limit, 0)
        if target == 0:
            return []

        page = 1
        total = target
        request_limit = min(self.ranking_page_size, target)

        while len(rows) < target and len(rows) < total:
            page_rows: list[MarketSymbolSnapshot] | None = None
            page_total = 0
            last_error: Exception | None = None
            for _ in range(self.ranking_page_retry_limit + 1):
                try:
                    page_rows, page_total = self._fetch_ranked_page(
                        fid=fid,
                        descending=descending,
                        limit=request_limit,
                        page=page,
                    )
                    last_error = None
                    break
                except Exception as error:
                    last_error = error

            if last_error is not None:
                logger.warning(
                    "EastMoney overview ranked page interrupted fid=%s descending=%s page=%s collected=%s error=%s",
                    fid,
                    descending,
                    page,
                    len(rows),
                    last_error,
                )
                break
            if page_rows is None:
                break
            if page == 1 and page_total > 0:
                total = min(page_total, target)
            if not page_rows:
                break

            added = 0
            for row in page_rows:
                if row.symbol in seen_symbols:
                    continue
                seen_symbols.add(row.symbol)
                rows.append(row)
                added += 1
                if len(rows) >= target:
                    break

            if added == 0 or len(page_rows) < request_limit:
                break
            page += 1

        return rows

    def _fetch_ranked_page(self, *, fid: str, descending: bool, limit: int, page: int) -> tuple[list[MarketSymbolSnapshot], int]:
        payload = self._get_json(
            self.ranking_endpoint,
            params={
                "pn": str(page),
                "pz": str(limit),
                "po": "1" if descending else "0",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": fid,
                "fields": "f12,f14,f2,f3,f6,f13,f100",
                "fs": self.market_scope,
            },
        )
        total = 0
        if isinstance(payload, dict):
            try:
                total = int(payload.get("data", {}).get("total", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                total = 0
        return self._parse_rows(payload), total

    def _fetch_northbound(self) -> float | None:
        payload = self._get_json(self.northbound_endpoint, params={"fields1": "f1,f3", "fields2": "f51,f52,f53,f54,f55,f56"})
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None

        direct_value = self._extract_number(data, ("northNetInflow", "northNetBuyAmt", "northNetAmt", "netInflow"))
        if direct_value is not None:
            return round(direct_value, 2)

        total = 0.0
        matched = False
        for key in ("hk2sh", "hk2sz", "沪股通", "深股通", "sh", "sz"):
            value = data.get(key)
            if isinstance(value, dict):
                nested = self._extract_number(value, ("netBuyAmt", "dayNetAmtIn", "netInflow", "inflow"))
                if nested is None:
                    continue
                total += nested
                matched = True
            elif isinstance(value, (int, float)):
                total += float(value)
                matched = True

        return round(total, 2) if matched else None

    def _get_json(self, url: str, *, params: dict[str, str]) -> dict[str, Any]:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return json.loads(response.text)

    def _parse_rows(self, payload: dict[str, Any]) -> list[MarketSymbolSnapshot]:
        diff = payload.get("data", {}).get("diff", []) or []
        snapshots: list[MarketSymbolSnapshot] = []
        for item in diff:
            code = str(item.get("f12", "")).strip()
            if not code:
                continue
            market = str(item.get("f13", "")).strip()
            snapshots.append(
                MarketSymbolSnapshot(
                    symbol=self._to_symbol(market, code),
                    code=code,
                    name=str(item.get("f14", code)).strip() or code,
                    price=self._to_optional_float(item.get("f2")),
                    change_percent=self._to_optional_float(item.get("f3")),
                    volume=self._to_float(item.get("f6")),
                    sector=str(item.get("f100", "")).strip() or None,
                )
            )
        return snapshots

    @staticmethod
    def _to_symbol(market: str, code: str) -> str:
        if market == "1":
            return f"sh{code}"
        if code.startswith(("8", "4")):
            return f"bj{code}"
        return f"sz{code}"

    @staticmethod
    def _to_optional_float(value: object) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number != 0 else 0.0

    @staticmethod
    def _to_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _extract_number(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = payload.get(key)
            try:
                if value is None:
                    continue
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _trading_progress_ratio(now: datetime | None = None) -> float:
        current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
        current_time = current.timetz().replace(tzinfo=None)
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)
        total_minutes = 240

        if current_time <= morning_start:
            return 1.0
        if current_time >= afternoon_end:
            return 1.0

        elapsed = 0
        if current_time > morning_start:
            elapsed += min(
                int((datetime.combine(current.date(), min(current_time, morning_end)) - datetime.combine(current.date(), morning_start)).total_seconds() // 60),
                120,
            )
        if current_time > afternoon_start:
            elapsed += min(
                int((datetime.combine(current.date(), min(current_time, afternoon_end)) - datetime.combine(current.date(), afternoon_start)).total_seconds() // 60),
                120,
            )

        progress = max(min(elapsed / total_minutes, 1.0), 0.15)
        return progress if progress > 0 else 1.0
