from __future__ import annotations

import logging
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.market.providers.base import (
    MarketBreadthBucketSnapshot,
    MarketBreadthDistributionSnapshot,
    MarketOverviewProvider,
    MarketOverviewSnapshot,
    MarketSymbolSnapshot,
    MarketTurnoverSnapshot,
)

logger = logging.getLogger(__name__)


class EastMoneyOverviewProvider(MarketOverviewProvider):
    name = "eastmoney"
    index_endpoint = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    ranking_endpoint = "https://push2.eastmoney.com/api/qt/clist/get"
    northbound_endpoint = "https://push2.eastmoney.com/api/qt/kamt/get"

    index_targets: list[tuple[str, str]] = [
        ("上证指数", "1.000001"),
        ("深证成指", "0.399001"),
        ("创业板指", "0.399006"),
    ]
    market_scope = "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23"
    market_distribution_limit = 6000
    request_headers = {
        "Referer": "https://quote.eastmoney.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    def fetch_overview(self) -> MarketOverviewSnapshot:
        market_rows = self._safe_fetch_ranked(fid="f3", descending=True, limit=self.market_distribution_limit)
        limit_up_candidates = self._safe_fetch_ranked(fid="f3", descending=True, limit=200)
        limit_down_candidates = self._safe_fetch_ranked(fid="f3", descending=False, limit=200)

        limit_up_sample = [item for item in limit_up_candidates if (item.change_percent or 0.0) >= 9.7][:5]
        limit_down_sample = [item for item in limit_down_candidates if (item.change_percent or 0.0) <= -9.7][:5]

        return MarketOverviewSnapshot(
            generated_at=datetime.now(UTC),
            source=self.name,
            indices=self._safe_fetch_indices(),
            top_gainers=self._safe_fetch_ranked(fid="f3", descending=True, limit=8),
            top_losers=self._safe_fetch_ranked(fid="f3", descending=False, limit=8),
            limit_up_total=len([item for item in limit_up_candidates if (item.change_percent or 0.0) >= 9.7]),
            limit_up_sample=limit_up_sample,
            limit_down_total=len([item for item in limit_down_candidates if (item.change_percent or 0.0) <= -9.7]),
            limit_down_sample=limit_down_sample,
            northbound_net_inflow=self._safe_fetch_northbound(),
            hot_stocks=self._safe_fetch_ranked(fid="f6", descending=True, limit=8),
            breadth_distribution=self._build_breadth_distribution(market_rows),
            turnover=self._build_turnover_snapshot(market_rows),
        )

    def _safe_fetch_indices(self) -> list[MarketSymbolSnapshot]:
        try:
            return self._fetch_indices()
        except Exception as error:
            logger.warning("EastMoney overview indices request failed: %s", error)
            return []

    def _safe_fetch_ranked(self, *, fid: str, descending: bool, limit: int) -> list[MarketSymbolSnapshot]:
        try:
            return self._fetch_ranked(fid=fid, descending=descending, limit=limit)
        except Exception as error:
            logger.warning(
                "EastMoney overview ranked request failed fid=%s descending=%s limit=%s error=%s",
                fid,
                descending,
                limit,
                error,
            )
            return []

    def _safe_fetch_northbound(self) -> float | None:
        try:
            return self._fetch_northbound()
        except Exception as error:
            logger.warning("EastMoney overview northbound request failed: %s", error)
            return None

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

    def _fetch_indices(self) -> list[MarketSymbolSnapshot]:
        payload = self._get_json(
            self.index_endpoint,
            params={
                "secids": ",".join(secid for _, secid in self.index_targets),
                "fields": "f12,f14,f2,f3,f6,f13,f100",
            },
        )
        return self._parse_rows(payload)

    def _fetch_ranked(self, *, fid: str, descending: bool, limit: int) -> list[MarketSymbolSnapshot]:
        payload = self._get_json(
            self.ranking_endpoint,
            params={
                "pn": "1",
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
        return self._parse_rows(payload)

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
        with httpx.Client(timeout=5.0, headers=self.request_headers) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()

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
