from __future__ import annotations

import inspect
import logging
import re
import socket
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from app.core.config import settings
from app.market.providers.base import (
    DragonTigerSeatSnapshot,
    DragonTigerStockSnapshot,
    NorthboundSummarySnapshot,
    ProviderProfile,
    ResearchProvider,
    ResearchStatusSnapshot,
    StockFundFlowSnapshot,
    capability,
)
from app.market.symbols import normalize_a_share_symbol

logger = logging.getLogger(__name__)


class ADataResearchProvider(ResearchProvider):
    name = "adata"
    profile = ProviderProfile(
        name=name,
        label="AData 研究数据",
        capabilities=(
            capability(
                "fund_flow",
                supported=True,
                fields=("main_net_inflow", "super_large_net_inflow", "large_net_inflow", "medium_net_inflow", "small_net_inflow", "main_net_ratio"),
                notes=("研究只读接口，不参与主行情链路",),
            ),
            capability("concept", supported=True, fields=("dragon_tiger_reason", "seat_name", "seat_net_amount"), notes=("龙虎榜/热点研究辅助字段",)),
            capability("fundamental", supported=True, fields=("stock_code", "short_name", "trade_date", "northbound_net_inflow"), notes=("首批仅暴露研究辅助摘要，不接主行情",)),
        ),
        stable_for_backtest=False,
        rate_limit_note="第三方研究接口，可能受频率和字段变动影响",
        failure_modes=("network_failure", "schema_change", "empty_response", "rate_limit", "dependency_error"),
    )

    def __init__(self, adata_module: Any | None = None, *, suppress_warnings: bool = False) -> None:
        self._adata = adata_module
        self.timeout_seconds = settings.adata_timeout_seconds
        self.suppress_warnings = suppress_warnings
        self.fund_flow_cache_ttl_seconds = settings.adata_fund_flow_cache_ttl_seconds
        self._fund_flow_cache: dict[str, tuple[datetime, StockFundFlowSnapshot]] = {}

    def fetch_stock_fund_flow(self, symbol: str) -> StockFundFlowSnapshot:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol:
            return StockFundFlowSnapshot(symbol=symbol, trade_date=None, source=self.name, status=ResearchStatusSnapshot(code="schema_change", notes="invalid_symbol"))

        cached = self._get_cached_fund_flow(normalized_symbol)
        if cached is not None:
            return cached

        try:
            module = self._load_adata()
        except Exception as error:
            return StockFundFlowSnapshot(
                symbol=normalized_symbol,
                trade_date=None,
                source=self.name,
                status=self._status_from_error(error),
            )

        started_at = perf_counter()
        try:
            rows = self._call_stock_fund_flow(normalized_symbol)
        except Exception as error:
            if not self.suppress_warnings:
                logger.warning("AData fund flow fetch failed symbol=%s error=%s", normalized_symbol, error)
            return StockFundFlowSnapshot(
                symbol=normalized_symbol,
                trade_date=None,
                source=self.name,
                status=self._status_from_error(error),
            )

        latency_ms = (perf_counter() - started_at) * 1000
        logger.debug("AData fund flow fetch symbol=%s latency_ms=%.2f", normalized_symbol, latency_ms)

        row = self._latest_row(rows)
        if row is None:
            snapshot = StockFundFlowSnapshot(
                symbol=normalized_symbol,
                trade_date=None,
                source=self.name,
                status=ResearchStatusSnapshot(code="empty_response"),
            )
            self._set_cached_fund_flow(normalized_symbol, snapshot)
            return snapshot

        snapshot = StockFundFlowSnapshot(
            symbol=normalized_symbol,
            trade_date=self._pick_trade_date(row),
            main_net_inflow=self._pick_float(row, ("主力净流入", "主力净额", "主力净流入额", "net_amount_main", "main_net_inflow")),
            super_large_net_inflow=self._pick_float(row, ("超大单净流入", "超大单净额", "net_amount_super", "max_net_inflow")),
            large_net_inflow=self._pick_float(row, ("大单净流入", "大单净额", "net_amount_large", "lg_net_inflow")),
            medium_net_inflow=self._pick_float(row, ("中单净流入", "中单净额", "net_amount_medium", "mid_net_inflow")),
            small_net_inflow=self._pick_float(row, ("小单净流入", "小单净额", "net_amount_small", "sm_net_inflow")),
            main_net_ratio=self._pick_float(row, ("主力净占比", "主力净流入占比", "net_ratio_main")),
            source=self.name,
            status=ResearchStatusSnapshot(code="ok"),
        )
        self._set_cached_fund_flow(normalized_symbol, snapshot)
        return snapshot

    def fetch_northbound_summary(self, start_date: str | None = None) -> NorthboundSummarySnapshot:
        try:
            module = self._load_adata()
            rows = self._call_northbound_flow(module, start_date=start_date)
        except Exception as error:
            logger.warning("AData northbound fetch failed start_date=%s error=%s", start_date, error)
            return NorthboundSummarySnapshot(source=self.name, status=self._status_from_error(error))

        row = self._latest_row(rows)
        if row is None:
            return NorthboundSummarySnapshot(source=self.name, status=ResearchStatusSnapshot(code="empty_response"))

        return NorthboundSummarySnapshot(
            net_inflow=self._pick_float(row, ("net_tgt", "net_amount", "northbound_net_inflow")),
            trade_date=self._pick_trade_date(row),
            source=self.name,
            status=ResearchStatusSnapshot(code="ok"),
        )

    def fetch_dragon_tiger(self, trade_date: str | None = None, symbol: str | None = None) -> list[DragonTigerStockSnapshot]:
        normalized_symbol = normalize_a_share_symbol(symbol) if symbol else None
        try:
            module = self._load_adata()
            rows = self._call_dragon_tiger(module, trade_date=trade_date, symbol=normalized_symbol)
        except Exception as error:
            logger.warning("AData dragon tiger fetch failed trade_date=%s symbol=%s error=%s", trade_date, normalized_symbol, error)
            return [
                DragonTigerStockSnapshot(
                    symbol=normalized_symbol or "",
                    stock_name="",
                    trade_date=trade_date or "",
                    source=self.name,
                    status=self._status_from_error(error),
                )
            ]

        payloads = self._normalize_rows(rows)
        if not payloads:
            return [
                DragonTigerStockSnapshot(
                    symbol=normalized_symbol or "",
                    stock_name="",
                    trade_date=trade_date or "",
                    source=self.name,
                    status=ResearchStatusSnapshot(code="empty_response"),
                )
            ]

        results: list[DragonTigerStockSnapshot] = []
        for headline in payloads:
            row_symbol = normalize_a_share_symbol(self._pick_text(headline, ("stock_code", "股票代码", "代码", "code")))
            if normalized_symbol and row_symbol != normalized_symbol:
                continue
            row_date = self._pick_trade_date(headline) or trade_date or ""
            seats = self._fetch_dragon_tiger_detail_seats(module, row_symbol, row_date) if row_symbol and row_date else []
            results.append(
                DragonTigerStockSnapshot(
                    symbol=row_symbol or "",
                    stock_name=self._pick_text(headline, ("short_name", "股票简称", "名称", "stock_name")),
                    trade_date=row_date,
                    reason=self._pick_text(headline, ("reason", "上榜原因", "reason_for_lhb")),
                    close_price=self._pick_float(headline, ("close", "收盘价", "close_price")),
                    change_percent=self._pick_float(headline, ("change_pct", "涨跌幅", "pct_chg", "change_cpt")),
                    turnover_rate=self._pick_float(headline, ("turnover_rate", "换手率")),
                    buy_amount=self._pick_float(headline, ("buy_amount", "买入金额", "买入额", "a_buy_amount")),
                    sell_amount=self._pick_float(headline, ("sell_amount", "卖出金额", "卖出额", "a_sell_amount")),
                    net_amount=self._pick_float(headline, ("net_amount", "净买入额", "净额", "net_buy_amount", "a_net_amount")),
                    seats=seats,
                    source=self.name,
                    status=ResearchStatusSnapshot(code="ok"),
                )
            )

        if not results:
            return [
                DragonTigerStockSnapshot(
                    symbol=normalized_symbol or "",
                    stock_name="",
                    trade_date=trade_date or "",
                    source=self.name,
                    status=ResearchStatusSnapshot(code="empty_response"),
                )
            ]

        return sorted(results, key=lambda item: (item.trade_date, abs(item.net_amount or 0.0)), reverse=True)

    def _call_stock_fund_flow(self, symbol: str) -> Any:
        try:
            from adata.stock.market.capital_flow.stock_capital_flow_east import StockCapitalFlowEast  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("adata east capital flow api unavailable") from error
        code = symbol[2:]
        return self._invoke_with_socket_timeout(StockCapitalFlowEast().get_capital_flow, stock_code=code)

    def _call_dragon_tiger(self, adata_module: Any, *, trade_date: str | None, symbol: str | None) -> Any:
        hot = getattr(getattr(getattr(adata_module, "sentiment", None), "hot", None), "list_a_list_daily", None)
        if hot is None:
            raise RuntimeError("adata dragon tiger api unavailable")
        kwargs: dict[str, Any] = {}
        if trade_date:
            kwargs.update({"report_date": trade_date, "trade_date": trade_date, "date": trade_date})
        return self._invoke_with_socket_timeout(self._invoke_best_effort, hot, kwargs)

    def _call_northbound_flow(self, adata_module: Any, *, start_date: str | None) -> Any:
        north = getattr(getattr(adata_module, "sentiment", None), "north", None)
        func = getattr(north, "north_flow", None)
        if func is None:
            raise RuntimeError("adata north flow api unavailable")
        return self._invoke_with_socket_timeout(self._invoke_best_effort, func, {"start_date": start_date})

    def _fetch_dragon_tiger_detail_seats(self, adata_module: Any, symbol: str, trade_date: str) -> list[DragonTigerSeatSnapshot]:
        func = getattr(getattr(getattr(adata_module, "sentiment", None), "hot", None), "get_a_list_info", None)
        if func is None:
            return []
        try:
            rows = self._invoke_with_socket_timeout(self._invoke_best_effort, func, {"stock_code": symbol[2:], "report_date": trade_date})
        except Exception as error:
            logger.warning("AData dragon tiger detail fetch failed symbol=%s trade_date=%s error=%s", symbol, trade_date, error)
            return []
        payloads = self._normalize_rows(rows)
        return self._build_seats(payloads)

    @staticmethod
    def _invoke_best_effort(func: Any, candidates: dict[str, Any]) -> Any:
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return func(**candidates)

        accepted = {
            name: value
            for name, value in candidates.items()
            if value not in (None, "") and name in signature.parameters
        }
        if accepted:
            return func(**accepted)
        return func()

    def _invoke_with_socket_timeout(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout_seconds)
        try:
            return func(*args, **kwargs)
        finally:
            socket.setdefaulttimeout(previous_timeout)

    def _get_cached_fund_flow(self, symbol: str) -> StockFundFlowSnapshot | None:
        if self.fund_flow_cache_ttl_seconds <= 0:
            return None
        cached = self._fund_flow_cache.get(symbol)
        if cached is None:
            return None
        cached_at, snapshot = cached
        if (datetime.now(UTC) - cached_at).total_seconds() > self.fund_flow_cache_ttl_seconds:
            self._fund_flow_cache.pop(symbol, None)
            return None
        return deepcopy(snapshot)

    def _set_cached_fund_flow(self, symbol: str, snapshot: StockFundFlowSnapshot) -> None:
        if self.fund_flow_cache_ttl_seconds <= 0:
            return
        self._fund_flow_cache[symbol] = (datetime.now(UTC), deepcopy(snapshot))

    def _load_adata(self) -> Any:
        if self._adata is not None:
            return self._adata
        try:
            import adata  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("adata is not installed") from error
        self._adata = adata
        return adata

    @staticmethod
    def _normalize_rows(payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if hasattr(payload, "to_dict"):
            try:
                return list(payload.to_dict("records"))
            except Exception:
                pass
        if isinstance(payload, dict):
            if "data" in payload:
                return ADataResearchProvider._normalize_rows(payload["data"])
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    @classmethod
    def _latest_row(cls, payload: Any) -> dict[str, Any] | None:
        rows = cls._normalize_rows(payload)
        if not rows:
            return None
        rows.sort(key=lambda row: cls._pick_trade_date(row) or "", reverse=True)
        return rows[0]

    @classmethod
    def _build_seats(cls, rows: list[dict[str, Any]]) -> list[DragonTigerSeatSnapshot]:
        seats: list[DragonTigerSeatSnapshot] = []
        for row in rows:
            seat_name = cls._pick_text(row, ("seat_name", "营业部名称", "营业部", "席位", "operate_name"))
            if not seat_name:
                continue
            buy_amount = cls._pick_float(row, ("amount", "成交金额", "买入金额", "a_buy_amount"))
            sell_amount = cls._pick_float(row, ("卖出金额", "a_sell_amount"))
            net_amount = cls._pick_float(row, ("net_amount", "净买入额", "净额", "a_net_amount"))
            if (buy_amount or 0) > (sell_amount or 0):
                role = "buy"
            elif (sell_amount or 0) > (buy_amount or 0):
                role = "sell"
            else:
                role = "net"
            seats.append(
                DragonTigerSeatSnapshot(
                    seat_name=seat_name,
                    role=role,
                    amount=max(buy_amount or 0.0, sell_amount or 0.0) if buy_amount is not None or sell_amount is not None else None,
                    net_amount=net_amount,
                    tag=cls._pick_text(row, ("tag", "类型", "席位类型", "operate_code")),
                )
            )
        return seats

    @staticmethod
    def _pick_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            if key in row and row[key] not in (None, ""):
                return str(row[key]).strip()
        return ""

    @classmethod
    def _pick_trade_date(cls, row: dict[str, Any]) -> str | None:
        for key in ("trade_date", "日期", "上榜日期", "date"):
            raw = row.get(key)
            if raw in (None, ""):
                continue
            text = str(raw).strip()
            if re.fullmatch(r"\d{8}", text):
                return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                return text
        return None

    @staticmethod
    def _pick_float(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
        for key in keys:
            if key not in row:
                continue
            value = row.get(key)
            parsed = ADataResearchProvider._to_float(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, "", "-", "--"):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).replace(",", "").replace("，", "").strip()
        multiplier = 1.0
        if text.endswith("亿"):
            multiplier = 1e8
            text = text[:-1]
        elif text.endswith("万"):
            multiplier = 1e4
            text = text[:-1]
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        return float(match.group()) * multiplier

    @staticmethod
    def _status_from_error(error: Exception) -> ResearchStatusSnapshot:
        message = str(error)
        lowered = message.lower()
        if any(marker in lowered for marker in ("connection", "dns", "resolve", "timeout", "timed out", "httpsconnectionpool", "max retries exceeded")):
            return ResearchStatusSnapshot(code="network_failure", notes=message)
        if "429" in lowered or "rate limit" in lowered or "too many" in lowered:
            return ResearchStatusSnapshot(code="rate_limit", notes=message)
        if "schema" in lowered or "column" in lowered or "field" in lowered:
            return ResearchStatusSnapshot(code="schema_change", notes=message)
        if "install" in lowered or "module" in lowered or "import" in lowered or "unavailable" in lowered:
            return ResearchStatusSnapshot(code="dependency_error", notes=message)
        return ResearchStatusSnapshot(code="network_failure", notes=message)

    @staticmethod
    def recent_trade_dates(days: int) -> list[str]:
        dates: list[str] = []
        now = datetime.now(UTC)
        for delta in range(max(days, 1) + 10):
            target = now - timedelta(days=delta)
            if target.weekday() >= 5:
                continue
            dates.append(target.strftime("%Y-%m-%d"))
            if len(dates) >= days:
                break
        return dates
