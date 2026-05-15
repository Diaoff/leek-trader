from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from itertools import product
from pathlib import Path
from time import perf_counter
from typing import Any

from app.backtest.execution import (
    ExecutionModel,
    apply_price_slippage,
    apply_impact_slippage,
    apply_volume_capacity,
    build_order_intent,
    buy_block_reason,
    resolve_execution_model,
    round_lot_shares,
    sell_block_reason,
)
from app.market.baostock_sync_service import BaoStockHistorySyncService
from app.market.data_service import MarketDataService
from app.market.history_storage import MarketDailyBarStorage
from app.market.provider_health import provider_health_tracker
from app.market.providers.base import DailyBarSnapshot
from app.market.quality_service import MarketDataQualityService
from app.market.source_health import MarketSourceHealthService
from app.market.symbols import normalize_a_share_symbol
from app.preferences.service import PreferenceService
from app.models.strategy import Strategy
from app.models.daily_review import DailyReview
from app.backtest.research_report import BACKTEST_RESEARCH_REPORT_VERSION, DEFAULT_LIMITATIONS, build_backtest_research_report
from app.strategy.contracts import StrategySignal
from app.strategy.plugins import StrategyPluginRegistry
from app.schemas.risk import RiskCheckResult, RiskDecision, RiskEvaluationResult, RiskSeverity
from app.trading.execution import ExecutionFill, calculate_execution_cost
from app.trading.reason_codes import (
    HOLD_SIGNAL,
    INSUFFICIENT_CASH_OR_LOT,
    MIN_CONFIDENCE_NOT_MET,
    MODEL_HOLD_OR_ZERO_TARGET,
    NO_POSITION_TO_EXIT,
    NO_REBALANCE_NEEDED,
    STANDARD_REASON_CODES,
    TARGET_DELTA_TOO_SMALL,
    ZERO_TARGET_POSITION,
    display_reason,
    normalize_reason_code,
)


@dataclass(slots=True)
class BacktestResult:
    status: str
    strategy_id: int | None
    strategy_name: str | None
    strategy_type: str
    symbol: str
    source: str
    adjustflag: str
    bars: int
    initial_cash: float
    final_net_worth: float
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    equity_curve: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    events: list[dict[str, Any]]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "symbol": self.symbol,
            "source": self.source,
            "adjustflag": self.adjustflag,
            "bars": self.bars,
            "initial_cash": self.initial_cash,
            "final_net_worth": self.final_net_worth,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "trade_count": self.trade_count,
            "equity_curve": self.equity_curve,
            "trades": self.trades,
            "events": self.events,
            "summary": self.summary,
        }


class BacktestService:
    LOCAL_DAILY_BAR_READ_OPERATION = "daily_bar_local_read"
    BACKTEST_SOFT_NO_TRADE_REASON_CODES = {
        HOLD_SIGNAL,
        MIN_CONFIDENCE_NOT_MET,
        MODEL_HOLD_OR_ZERO_TARGET,
        NO_POSITION_TO_EXIT,
        NO_REBALANCE_NEEDED,
        TARGET_DELTA_TOO_SMALL,
        ZERO_TARGET_POSITION,
    }
    BACKTEST_BLOCK_REASON_CODES = STANDARD_REASON_CODES - BACKTEST_SOFT_NO_TRADE_REASON_CODES

    def __init__(self) -> None:
        self.strategy_registry = StrategyPluginRegistry()
        self.preference_service = PreferenceService()

    def run_single_symbol_backtest(
        self,
        db,
        *,
        symbol: str,
        strategy_id: int | None = None,
        strategy_type: str = "moving_average",
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        initial_cash: float = 100000.0,
        commission_rate: float = 0.0003,
        min_commission: float = 5.0,
        stamp_tax_rate: float = 0.0005,
        slippage_rate: float = 0.0002,
        fixed_slippage_amount: float = 0.0,
        max_position_pct: float = 1.0,
        parameters: dict[str, Any] | None = None,
        limit_move_policy: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        user_id: int | None = None,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        strategy_name: str | None = None
        if strategy_id is not None:
            strategy = self._load_strategy(db, strategy_id=strategy_id, tenant_id=tenant_id, user_id=user_id)
            strategy_type = str(strategy.strategy_type.value if hasattr(strategy.strategy_type, "value") else strategy.strategy_type)
            strategy_name = strategy.name
            parameters = dict(strategy.parameters or {})

        if strategy_type == "rl_trading" and (parameters or {}).get("rl_policy_mode") == "trained_model" and user_id is not None:
            parameters = dict(parameters or {})
            parameters["model_registry_root"] = self._rl_model_registry_root(user_id)
        parameters = self._merge_execution_parameters(parameters, limit_move_policy=limit_move_policy, fixed_slippage_amount=fixed_slippage_amount)
        risk_rule_version = self._current_risk_rule_version(db, user_id)

        self._emit_progress(progress_callback, 1, 4, "准备回测参数", [f"标的：{symbol}", f"策略：{strategy_name or strategy_type}"])
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol:
            normalized_symbol = symbol.strip().lower()
        storage = MarketDailyBarStorage(db)
        self._emit_progress(progress_callback, 2, 4, "读取本地历史日线", [f"数据源：{source}", f"复权：{adjustflag}"])
        bars = self._load_stored_bars(
            storage,
            symbol=normalized_symbol,
            source=source,
            adjustflag=adjustflag,
            start_date=start_date,
            end_date=end_date,
        )
        sync_summary: dict[str, Any] | None = None
        if not bars:
            self._emit_progress(progress_callback, 2, 4, "本地无日线，开始同步", [f"日期：{start_date} ~ {end_date}"])
            sync_summary = self._sync_missing_history(
                db,
                symbol=normalized_symbol,
                source=source,
                adjustflag=adjustflag,
                start_date=start_date,
                end_date=end_date,
            )
            if sync_summary.get("attempted"):
                self._emit_progress(progress_callback, 3, 4, "同步完成，重新读取日线", [f"状态：{sync_summary.get('status', 'skipped')}", f"入库：{sync_summary.get('bars_upserted', 0)} 条"])
                bars = self._load_stored_bars(
                    storage,
                    symbol=normalized_symbol,
                    source=source,
                    adjustflag=adjustflag,
                    start_date=start_date,
                    end_date=end_date,
                )
        if not bars:
            reason = "no_records_after_sync" if sync_summary and sync_summary.get("attempted") else "no_records"
            summary: dict[str, Any] = {"reason": reason}
            if sync_summary is not None:
                summary["history_sync"] = sync_summary
            result = BacktestResult(
                status="empty",
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                strategy_type=strategy_type,
                symbol=normalized_symbol,
                source=source,
                adjustflag=adjustflag,
                bars=0,
                initial_cash=initial_cash,
                final_net_worth=initial_cash,
                total_return_pct=0.0,
                max_drawdown_pct=0.0,
                trade_count=0,
                equity_curve=[],
                trades=[],
                events=[],
                summary={**summary, "risk_rule_version": risk_rule_version},
            ).to_dict()
            self._attach_research_outputs(
                db,
                result=result,
                symbol=normalized_symbol,
                source=source,
                adjustflag=adjustflag,
                start_date=start_date,
                end_date=end_date,
                commission_rate=commission_rate,
                min_commission=min_commission,
                stamp_tax_rate=stamp_tax_rate,
                slippage_rate=slippage_rate,
                fixed_slippage_amount=fixed_slippage_amount,
                max_position_pct=max_position_pct,
            )
            return result

        self._emit_progress(progress_callback, 3, 4, "执行策略回放", [f"样本：{len(bars)} 根"])
        plugin = self.strategy_registry.get(strategy_type)
        strategy_parameters = self._backtest_parameters(strategy_type, parameters or {})
        result = self._simulate_events(
            bars=bars,
            plugin_name=plugin.name,
            plugin=plugin,
            parameters=strategy_parameters,
            initial_cash=initial_cash,
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_tax_rate=stamp_tax_rate,
            slippage_rate=slippage_rate,
            fixed_slippage_amount=fixed_slippage_amount,
            max_position_pct=max_position_pct,
            source=source,
            adjustflag=adjustflag,
            risk_rule_version=risk_rule_version,
        )
        result["strategy_type"] = strategy_type
        result["strategy_id"] = strategy_id
        result["strategy_name"] = strategy_name
        result["symbol"] = normalized_symbol
        result["source"] = source
        result["adjustflag"] = adjustflag
        if sync_summary is not None:
            result.setdefault("summary", {})["history_sync"] = sync_summary
        result.setdefault("summary", {})["risk_rule_version"] = risk_rule_version
        self._attach_research_outputs(
            db,
            result=result,
            symbol=normalized_symbol,
            source=source,
            adjustflag=adjustflag,
            start_date=start_date,
            end_date=end_date,
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_tax_rate=stamp_tax_rate,
            slippage_rate=slippage_rate,
            fixed_slippage_amount=fixed_slippage_amount,
            max_position_pct=max_position_pct,
        )
        return result

    @staticmethod
    def _load_strategy(db, *, strategy_id: int, tenant_id: str | None, user_id: int | None) -> Strategy:
        query = db.query(Strategy).filter(Strategy.id == strategy_id)
        if tenant_id is not None:
            query = query.filter(Strategy.tenant_id == tenant_id)
        if user_id is not None:
            query = query.filter(Strategy.user_id == user_id)
        strategy = query.first()
        if strategy is None:
            raise ValueError("strategy not found")
        return strategy

    @staticmethod
    def _rl_model_registry_root(user_id: int) -> Path:
        return Path(__file__).resolve().parents[3] / "artifacts" / "rl_models" / f"user-{user_id}"

    @staticmethod
    def _emit_progress(callback: Any | None, step: int, total: int, label: str, details: list[str] | None = None) -> None:
        if callback is not None:
            callback(step, total, label, details or [])

    @staticmethod
    def _load_stored_bars(
        storage: MarketDailyBarStorage,
        *,
        symbol: str,
        source: str,
        adjustflag: str,
        start_date: date | None,
        end_date: date | None,
    ) -> list[DailyBarSnapshot]:
        started_at = perf_counter()
        try:
            bars = storage.list_bars(
                symbol=symbol,
                source=source,
                adjustflag=adjustflag,
                start_date=start_date,
                end_date=end_date,
            ).bars
        except Exception as error:
            provider_health_tracker.record(
                source=source,
                operation=BacktestService.LOCAL_DAILY_BAR_READ_OPERATION,
                status="failure",
                latency_ms=(perf_counter() - started_at) * 1000,
                error_message=str(error),
            )
            raise
        provider_health_tracker.record(
            source=source,
            operation=BacktestService.LOCAL_DAILY_BAR_READ_OPERATION,
            status="success" if bars else "empty",
            latency_ms=(perf_counter() - started_at) * 1000,
            row_count=len(bars),
        )
        return bars

    @staticmethod
    def _sync_missing_history(
        db,
        *,
        symbol: str,
        source: str,
        adjustflag: str,
        start_date: date | None,
        end_date: date | None,
    ) -> dict[str, Any]:
        if source != "baostock" or start_date is None or end_date is None:
            return {
                "attempted": False,
                "reason": "sync_requires_baostock_source_and_date_range",
                "source": source,
                "adjustflag": adjustflag,
            }
        try:
            result = BaoStockHistorySyncService(db).sync_history(
                symbols=[symbol],
                start_date=start_date,
                end_date=end_date,
                adjustflag=adjustflag,
                incremental=False,
            )
        except Exception as error:
            return {
                "attempted": True,
                "status": "failed",
                "source": source,
                "adjustflag": adjustflag,
                "error": str(error),
            }
        payload = result.to_dict()
        if int(payload.get("bars_upserted") or 0) <= 0:
            fallback_payload = BacktestService._sync_fallback_history(
                db,
                symbol=symbol,
                adjustflag=adjustflag,
                start_date=start_date,
                end_date=end_date,
                previous_sync=payload,
            )
            if fallback_payload is not None:
                return fallback_payload
        return {"attempted": True, **payload}

    @staticmethod
    def _sync_fallback_history(
        db,
        *,
        symbol: str,
        adjustflag: str,
        start_date: date,
        end_date: date,
        previous_sync: dict[str, Any],
    ) -> dict[str, Any] | None:
        limit = max((end_date - start_date).days + 20, 60)
        payload = MarketDataService().get_daily_bars_with_source(symbol, limit=limit, force_refresh=True, source=None)
        bars = [bar for bar in payload.bars if start_date <= bar.trade_date <= end_date]
        if not bars:
            return None
        upserted = MarketDailyBarStorage(db).upsert_bars(bars, source="baostock", adjustflag=adjustflag)
        return {
            "attempted": True,
            "status": "fallback_success",
            "source": "baostock",
            "adjustflag": adjustflag,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "requested_symbols": [symbol],
            "incremental": False,
            "resolved_ranges": [
                {
                    "symbol": symbol,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "skipped": False,
                    "reason": "fallback_provider",
                }
            ],
            "succeeded_symbols": [symbol],
            "success_count": 1,
            "failure_count": 0,
            "failures": [],
            "bars_upserted": upserted,
            "fallback_source": payload.source,
            "primary_sync": previous_sync,
        }

    @staticmethod
    def _backtest_parameters(strategy_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(parameters)
        if strategy_type == "moving_average":
            normalized.setdefault("allow_backtest_trend_entry", True)
            normalized.setdefault("backtest_trend_entry_min_bars", 0)
            normalized.setdefault("volume_confirm_ratio", 0.5)
            normalized.setdefault("max_volatility_20", 0.5)
            normalized.setdefault("bypass_manager_buy_filter", True)
        if strategy_type == "macd":
            normalized.setdefault("allow_backtest_trend_entry", True)
            normalized.setdefault("backtest_trend_entry_min_bars", 0)
            normalized.setdefault("volume_confirm_ratio", 0.5)
            normalized.setdefault("max_volatility_20", 0.5)
        if strategy_type == "rl_trading":
            normalized.setdefault("rl_policy_mode", "baseline")
            normalized.setdefault("baseline_buy_trend_threshold", 0.0)
            normalized.setdefault("baseline_buy_requires_bullish", False)
            normalized.setdefault("min_confidence", 0.0)
        if strategy_type == "rsi_reversal":
            normalized.setdefault("rsi_period", 14)
            normalized.setdefault("oversold", 30)
            normalized.setdefault("overbought", 70)
        if strategy_type == "bollinger_band":
            normalized.setdefault("boll_period", 20)
            normalized.setdefault("stddev_multiplier", 2)
        if strategy_type == "kdj_momentum":
            normalized.setdefault("kdj_period", 9)
            normalized.setdefault("k_smoothing", 3)
            normalized.setdefault("d_smoothing", 3)
        if strategy_type == "signal_fusion":
            normalized.setdefault("min_confidence", 0.55)
            normalized.setdefault("conflict_hold_threshold", 0.2)
        return normalized

    def _attach_research_outputs(
        self,
        db,
        *,
        result: dict[str, Any],
        symbol: str,
        source: str,
        adjustflag: str,
        start_date: date | None,
        end_date: date | None,
        commission_rate: float,
        min_commission: float,
        stamp_tax_rate: float,
        slippage_rate: float,
        fixed_slippage_amount: float,
        max_position_pct: float,
    ) -> None:
        summary = result.setdefault("summary", {})
        summary["research_summary"] = self._build_research_summary(
            db,
            result=result,
            symbol=symbol,
            source=source,
            adjustflag=adjustflag,
            start_date=start_date,
            end_date=end_date,
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_tax_rate=stamp_tax_rate,
            slippage_rate=slippage_rate,
            fixed_slippage_amount=fixed_slippage_amount,
            max_position_pct=max_position_pct,
        )
        summary["research_report"] = build_backtest_research_report(result)

    def _build_research_summary(
        self,
        db,
        *,
        result: dict[str, Any],
        symbol: str,
        source: str,
        adjustflag: str,
        start_date: date | None,
        end_date: date | None,
        commission_rate: float,
        min_commission: float,
        stamp_tax_rate: float,
        slippage_rate: float,
        fixed_slippage_amount: float,
        max_position_pct: float,
    ) -> dict[str, Any]:
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        diagnostics = summary.get("diagnostics") if isinstance(summary.get("diagnostics"), dict) else {}
        execution_model = summary.get("execution_model") if isinstance(summary.get("execution_model"), dict) else {}
        history_sync = summary.get("history_sync") if isinstance(summary.get("history_sync"), dict) else {}
        source_health_report = MarketSourceHealthService(db).build_daily_bar_source_health(
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date,
            adjustflag=adjustflag,
            sources=[source],
        ).to_dict()
        quality_report = MarketDataQualityService(db).build_daily_bar_quality_report(
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date,
            source=source,
            adjustflag=adjustflag,
        ).to_dict()
        source_item = next(iter(source_health_report.get("sources") or []), {})
        quality_item = next(iter(quality_report.get("symbol_reports") or []), {})
        null_fields = [
            key
            for key, value in (quality_item.get("null_counts") or {}).items()
            if int(value or 0) > 0
        ]
        warnings = self._research_warnings(
            result=result,
            history_sync=history_sync,
            source_item=source_item,
            quality_item=quality_item,
            null_fields=null_fields,
        )
        return {
            "report_version": BACKTEST_RESEARCH_REPORT_VERSION,
            "empty_result": result.get("status") == "empty",
            "sample": {
                "start_date": summary.get("first_trade_date") or (start_date.isoformat() if start_date else None),
                "end_date": summary.get("last_trade_date") or (end_date.isoformat() if end_date else None),
                "bars": result.get("bars", 0),
            },
            "data_source": {
                "requested_source": source,
                "used_source": source,
                "adjustflag": adjustflag,
                "source_health_level": source_item.get("health_level"),
                "runtime_health_level": source_item.get("runtime_health_level"),
                "coverage_ratio": source_item.get("coverage_ratio"),
                "field_missing_ratio": source_item.get("field_missing_ratio"),
                "last_trade_date": source_item.get("last_trade_date"),
                "history_sync_status": history_sync.get("status"),
                "history_sync_error": history_sync.get("error"),
                "fallback_source": history_sync.get("fallback_source"),
                "notes": list(source_item.get("notes") or []),
                "empty_result": result.get("status") == "empty",
            },
            "quality": {
                "status": quality_report.get("status"),
                "rows": quality_item.get("rows", 0),
                "suspended_rows": quality_item.get("suspended_rows", 0),
                "st_rows": quality_item.get("st_rows", 0),
                "null_field_count": len(null_fields),
                "null_fields": null_fields,
                "notes": self._quality_notes(quality_item=quality_item, null_fields=null_fields),
            },
            "cost_model": {
                "commission_rate": commission_rate,
                "min_commission": min_commission,
                "stamp_tax_rate": stamp_tax_rate,
                "slippage_rate": execution_model.get("slippage_rate", slippage_rate),
                "fixed_slippage_amount": execution_model.get("fixed_slippage_amount", fixed_slippage_amount),
                "impact_slippage_factor": execution_model.get("impact_slippage_factor", 0.0),
                "total_fees": summary.get("total_fees", 0.0),
                "total_slippage_cost": summary.get("total_slippage_cost", 0.0),
            },
            "execution_constraints": {
                "engine_version": BACKTEST_RESEARCH_REPORT_VERSION,
                "lot_size": execution_model.get("lot_size", 100),
                "max_volume_participation": execution_model.get("max_volume_participation"),
                "limit_move_policy": execution_model.get("limit_move_policy", {}),
                "max_position_pct": max_position_pct,
                "total_unfilled_shares": summary.get("total_unfilled_shares", 0),
            },
            "warnings": warnings,
            "limitations": list(DEFAULT_LIMITATIONS),
            "diagnostics": {
                "zero_trade": bool(diagnostics.get("zero_trade")),
                "no_trade_reason_counts": diagnostics.get("no_trade_reason_counts", {}),
            },
        }

    @staticmethod
    def _quality_notes(*, quality_item: dict[str, Any], null_fields: list[str]) -> list[str]:
        notes: list[str] = []
        if int(quality_item.get("rows") or 0) <= 0:
            notes.append("指定区间没有落库日线样本。")
        if int(quality_item.get("suspended_rows") or 0) > 0:
            notes.append(f"样本中包含 {quality_item.get('suspended_rows')} 根停牌或异常状态日线。")
        if int(quality_item.get("st_rows") or 0) > 0:
            notes.append(f"样本中包含 {quality_item.get('st_rows')} 根 ST 日线，涨跌停规则更严格。")
        if null_fields:
            notes.append(f"存在缺失字段：{', '.join(null_fields[:4])}")
        return notes

    @staticmethod
    def _research_warnings(
        *,
        result: dict[str, Any],
        history_sync: dict[str, Any],
        source_item: dict[str, Any],
        quality_item: dict[str, Any],
        null_fields: list[str],
    ) -> list[str]:
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        diagnostics = summary.get("diagnostics") if isinstance(summary.get("diagnostics"), dict) else {}
        warnings: list[str] = []
        if result.get("status") == "empty" or int(result.get("bars") or 0) <= 0:
            warnings.append("历史数据不足：指定区间没有可用日线样本，当前报告不能评价策略有效性。")
        sync_status = str(history_sync.get("status") or "")
        if sync_status == "fallback_success":
            fallback_source = history_sync.get("fallback_source") or "fallback"
            warnings.append(f"数据源发生降级：主同步未直接返回样本，已通过 {fallback_source} 回填。")
        elif sync_status == "failed":
            warnings.append(f"历史数据同步失败：{history_sync.get('error') or '未知错误'}。")
        if str(source_item.get("health_level") or "") in {"degraded", "down"}:
            warnings.append(f"数据源健康度为 {source_item.get('health_level')}，应降低对该次回测的结论置信度。")
        if null_fields:
            warnings.append(f"行情字段存在缺失：{', '.join(null_fields[:4])}。")
        if int(quality_item.get("suspended_rows") or 0) > 0:
            warnings.append("样本含停牌或异常交易日，成交约束对结果影响更强。")
        if bool(diagnostics.get("zero_trade")):
            warnings.append("零成交：当前样本内没有形成可执行成交，收益和风险指标解释力有限。")
        if int(summary.get("total_unfilled_shares") or 0) > 0:
            warnings.append(f"成交受限：累计 {int(summary.get('total_unfilled_shares') or 0)} 股未成交。")
        no_trade_counts = diagnostics.get("no_trade_reason_counts") if isinstance(diagnostics.get("no_trade_reason_counts"), dict) else {}
        if int(no_trade_counts.get("insufficient_history") or 0) > 0:
            warnings.append("样本前段存在历史长度不足阶段，部分信号只能观望。")
        deduped: list[str] = []
        for item in warnings:
            if item not in deduped:
                deduped.append(item)
        return deduped

    def _simulate_events(
        self,
        *,
        bars: list[DailyBarSnapshot],
        plugin_name: str,
        plugin,
        parameters: dict[str, Any],
        initial_cash: float,
        commission_rate: float,
        min_commission: float,
        stamp_tax_rate: float,
        slippage_rate: float,
        fixed_slippage_amount: float = 0.0,
        max_position_pct: float,
        source: str,
        adjustflag: str,
        risk_rule_version: str | None = None,
    ) -> dict[str, Any]:
        cash = initial_cash
        shares = 0
        peak = initial_cash
        previous_net_worth = initial_cash
        total_fees = 0.0
        today_bought_shares = 0
        last_trade_date: date | None = None
        execution_model = resolve_execution_model(parameters, slippage_rate=slippage_rate)
        total_unfilled_shares = 0
        total_slippage_cost = 0.0
        trades: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []

        for index, bar in enumerate(bars):
            if last_trade_date != bar.trade_date:
                today_bought_shares = 0
                last_trade_date = bar.trade_date
            history = bars[: index + 1]
            evaluated_signal = plugin.evaluate(str(bar.symbol), history, parameters)
            standard_signal = StrategySignal.coerce(evaluated_signal)
            signal = standard_signal.to_legacy()
            action = standard_signal.action
            rl_action = signal.get("rl_action") if isinstance(signal.get("rl_action"), dict) else {}
            raw_target_pct = float((rl_action or {}).get("raw_target_position_pct") or signal.get("position_pct") or 0.0)
            trigger_reason = standard_signal.trigger_reason
            target_pct = standard_signal.position_pct
            if action == "buy":
                target_pct = min(target_pct or 0.1, max_position_pct)
            elif action in {"sell", "reduce"}:
                target_pct = 0.0 if action == "sell" else min(shares * float(bar.close_price) / (cash + shares * float(bar.close_price)) if cash + shares * float(bar.close_price) > 0 else 0.0, max_position_pct)
            else:
                target_pct = shares * float(bar.close_price) / (cash + shares * float(bar.close_price)) if cash + shares * float(bar.close_price) > 0 else 0.0

            close_price = float(bar.close_price)
            execution_price = apply_price_slippage(
                close_price,
                side="buy" if action == "buy" else "sell" if action in {"sell", "reduce"} else "hold",
                model=execution_model,
            )
            net_worth = cash + shares * close_price
            target_value = net_worth * target_pct
            current_value = shares * close_price
            delta_value = target_value - current_value
            shares_delta = 0
            fee = 0.0
            requested_shares_delta = 0
            unfilled_shares = 0
            block_reason: str | None = None

            if delta_value > close_price:
                block_reason = buy_block_reason(bar, model=execution_model)
                if block_reason is None:
                    bought = int(delta_value / execution_price)
                    affordable = int(cash / execution_price)
                    requested_shares_delta = round_lot_shares(max(0, min(bought, affordable)), lot_size=execution_model.lot_size)
                    shares_delta = apply_volume_capacity(requested_shares_delta, bar, execution_model)
                    if shares_delta > 0:
                        execution_price = apply_impact_slippage(
                            execution_price,
                            bar,
                            shares=shares_delta,
                            side="buy",
                            model=execution_model,
                        )
                        impact_affordable = self._max_affordable_buy_shares(
                            cash=cash,
                            price=execution_price,
                            lot_size=execution_model.lot_size,
                            commission_rate=commission_rate,
                            min_commission=min_commission,
                            stamp_tax_rate=stamp_tax_rate,
                        )
                        shares_delta = min(shares_delta, impact_affordable)
                        if shares_delta > 0:
                            execution_price = apply_impact_slippage(
                                apply_price_slippage(close_price, side="buy", model=execution_model),
                                bar,
                                shares=shares_delta,
                                side="buy",
                                model=execution_model,
                            )
                    unfilled_shares = max(requested_shares_delta - shares_delta, 0)
                    if shares_delta > 0:
                        cost = calculate_execution_cost(
                            quantity=shares_delta,
                            price=execution_price,
                            side="buy",
                            commission_rate=commission_rate,
                            min_commission=min_commission,
                            stamp_tax_rate=stamp_tax_rate,
                        )
                        trade_value = float(cost.trade_value)
                        fee = float(cost.total_fee)
                        cash -= trade_value + fee
                        shares += shares_delta
                        today_bought_shares += shares_delta
            elif delta_value < -close_price and shares > 0:
                sellable_shares = max(shares - today_bought_shares, 0)
                block_reason = sell_block_reason(bar, sellable_shares=sellable_shares, model=execution_model)
                if block_reason is None:
                    sold = min(sellable_shares, int(abs(delta_value) / execution_price))
                    requested_shares_delta = -round_lot_shares(sold, lot_size=execution_model.lot_size)
                    sold = apply_volume_capacity(abs(requested_shares_delta), bar, execution_model)
                    shares_delta = -sold
                    unfilled_shares = max(abs(requested_shares_delta) - sold, 0)
                    if sold > 0:
                        execution_price = apply_impact_slippage(
                            execution_price,
                            bar,
                            shares=sold,
                            side="sell",
                            model=execution_model,
                        )
                        cost = calculate_execution_cost(
                            quantity=sold,
                            price=execution_price,
                            side="sell",
                            commission_rate=commission_rate,
                            min_commission=min_commission,
                            stamp_tax_rate=stamp_tax_rate,
                        )
                        trade_value = float(cost.trade_value)
                        fee = float(cost.total_fee)
                        cash += trade_value - fee
                        shares -= sold

            no_trade_reason = self._no_trade_reason(
                action=action,
                shares=shares,
                shares_delta=shares_delta,
                raw_target_pct=raw_target_pct,
                target_pct=target_pct,
                delta_value=delta_value,
                close_price=close_price,
                trigger_reason=trigger_reason,
                block_reason=block_reason,
            )
            rejection_code = no_trade_reason
            risk_evaluation = self._build_risk_evaluation(
                no_trade_reason=no_trade_reason,
                requested_shares_delta=requested_shares_delta,
                shares_delta=shares_delta,
                unfilled_shares=unfilled_shares,
                risk_rule_version=risk_rule_version,
            )

            total_fees += fee
            total_unfilled_shares += unfilled_shares
            if shares_delta != 0:
                total_slippage_cost += abs(shares_delta) * abs(execution_price - close_price)
            position_value = shares * close_price
            net_worth = cash + position_value
            peak = max(peak, net_worth)
            drawdown_pct = 0.0 if peak <= 0 else (peak - net_worth) / peak * 100
            turnover_pct = 0.0 if initial_cash <= 0 else abs(shares_delta) * execution_price / initial_cash * 100

            events.append(
                {
                    "trade_date": str(bar.trade_date),
                    "signal": action,
                    "strategy": plugin_name,
                    "trigger_reason": trigger_reason,
                    "confidence": signal.get("confidence"),
                    "component_signals": signal.get("component_signals"),
                    "fusion_score": signal.get("fusion_score"),
                    "fusion_confidence": signal.get("fusion_confidence"),
                    "standard_signal": standard_signal.to_dict(),
                    "rl_action_type": (rl_action or {}).get("action_type"),
                    "raw_target_position_pct": round(raw_target_pct, 6),
                    "target_position_pct": round(target_pct, 6),
                    "shares_delta": shares_delta,
                    "requested_shares_delta": requested_shares_delta,
                    "unfilled_shares": unfilled_shares,
                    "no_trade_reason": no_trade_reason,
                    "rejection_code": rejection_code,
                    "risk_rule_version": risk_rule_version,
                    "risk_decision": risk_evaluation.decision.value,
                    "rejection_reason": risk_evaluation.rejection_reason,
                    "risk_checks": risk_evaluation.legacy_checks(),
                    "risk_evaluation": risk_evaluation.model_dump(),
                    "execution_price": round(execution_price, 6),
                }
            )
            if shares_delta != 0:
                intent = build_order_intent(
                    symbol=str(bar.symbol),
                    side="buy" if shares_delta > 0 else "sell",
                    requested_quantity=abs(requested_shares_delta),
                    price_reference=round(execution_price, 6),
                    mode="backtest",
                )
                execution_fill = ExecutionFill.from_intent(
                    intent,
                    filled_quantity=abs(shares_delta),
                    price=round(execution_price, 6),
                    fee=round(fee, 4),
                ).to_dict()
                trades.append(
                    {
                        "trade_date": str(bar.trade_date),
                        "side": "buy" if shares_delta > 0 else "sell",
                        "shares_delta": shares_delta,
                        "requested_shares_delta": requested_shares_delta,
                        "unfilled_shares": unfilled_shares,
                        "risk_rule_version": risk_rule_version,
                        "risk_decision": risk_evaluation.decision.value,
                        "rejection_reason": risk_evaluation.rejection_reason,
                        "risk_checks": risk_evaluation.legacy_checks(),
                        "risk_evaluation": risk_evaluation.model_dump(),
                        "execution_price": round(execution_price, 6),
                        "fee": round(fee, 4),
                        "execution": execution_fill,
                    }
                )

            equity_curve.append(
                {
                    "trade_date": str(bar.trade_date),
                    "net_worth": round(net_worth, 4),
                    "cash": round(cash, 4),
                    "position_value": round(position_value, 4),
                    "position_pct": round(position_value / net_worth, 6) if net_worth else 0.0,
                    "drawdown_pct": round(drawdown_pct, 6),
                    "turnover_pct": round(turnover_pct, 6),
                    "signal": action,
                }
            )
            previous_net_worth = net_worth

        final_net_worth = equity_curve[-1]["net_worth"] if equity_curve else initial_cash
        max_drawdown_pct = max((row["drawdown_pct"] for row in equity_curve), default=0.0)
        total_return_pct = 0.0 if initial_cash <= 0 else (final_net_worth - initial_cash) / initial_cash * 100
        report = self._build_report(
            equity_curve=equity_curve,
            trades=trades,
            initial_cash=initial_cash,
            total_fees=total_fees,
        )
        diagnostics = self._build_diagnostics(events, trades)
        result = BacktestResult(
            status="completed",
            strategy_id=None,
            strategy_name=None,
            strategy_type=plugin_name,
            symbol=str(bars[0].symbol),
            source=source,
            adjustflag=adjustflag,
            bars=len(bars),
            initial_cash=initial_cash,
            final_net_worth=final_net_worth,
            total_return_pct=round(total_return_pct, 6),
            max_drawdown_pct=round(max_drawdown_pct, 6),
            trade_count=len(trades),
            equity_curve=equity_curve,
            trades=trades,
            events=events,
            summary={
                "strategy_name": plugin_name,
                "parameters": self._public_parameters(parameters),
                "bars": len(bars),
                "risk_rule_version": risk_rule_version,
                "total_fees": round(total_fees, 4),
                "total_unfilled_shares": total_unfilled_shares,
                "total_slippage_cost": round(total_slippage_cost, 4),
                "execution_model": execution_model.to_dict(),
                "first_trade_date": str(bars[0].trade_date),
                "last_trade_date": str(bars[-1].trade_date),
                "diagnostics": diagnostics,
                "report": report,
            },
        ).to_dict()
        result["summary"]["research_report"] = build_backtest_research_report(result)
        return result

    def _build_risk_evaluation(
        self,
        *,
        no_trade_reason: str | None,
        requested_shares_delta: int,
        shares_delta: int,
        unfilled_shares: int,
        risk_rule_version: str | None,
    ) -> RiskEvaluationResult:
        reason_code = normalize_reason_code(no_trade_reason)
        if shares_delta != 0:
            checks: list[RiskCheckResult] = [
                RiskCheckResult(
                    rule_id="backtest_execution_fill",
                    passed=True,
                    severity=RiskSeverity.INFO,
                    suggested_action="continue",
                    explanation="backtest order filled",
                    threshold=requested_shares_delta,
                    actual=shares_delta,
                    metadata={"reason_code": reason_code, "unfilled_shares": unfilled_shares},
                    rule_version=risk_rule_version,
                )
            ]
            if unfilled_shares > 0:
                checks.append(
                    RiskCheckResult(
                        rule_id="warn_backtest_unfilled_shares",
                        passed=True,
                        severity=RiskSeverity.WARN,
                        suggested_action="review_liquidity",
                        explanation="backtest order partially filled",
                        threshold=requested_shares_delta,
                        actual=shares_delta,
                        metadata={"reason_code": reason_code, "unfilled_shares": unfilled_shares},
                        rule_version=risk_rule_version,
                    )
                )
            return RiskEvaluationResult(
                passed=True,
                decision=RiskDecision.WARN if unfilled_shares > 0 else RiskDecision.PASS,
                checks=checks,
                rejection_reason=None,
                risk_rule_version=risk_rule_version,
            )

        explanation = display_reason(reason_code) if reason_code is not None else "backtest no trade"
        if reason_code in self.BACKTEST_BLOCK_REASON_CODES:
            return RiskEvaluationResult(
                passed=False,
                decision=RiskDecision.REJECT,
                checks=[
                    RiskCheckResult(
                        rule_id=f"backtest_block_{reason_code}",
                        passed=False,
                        severity=RiskSeverity.HARD,
                        suggested_action="reject_order",
                        explanation=explanation,
                        threshold=requested_shares_delta,
                        actual=shares_delta,
                        metadata={"reason_code": reason_code},
                        rule_version=risk_rule_version,
                    )
                ],
                rejection_reason=explanation,
                risk_rule_version=risk_rule_version,
            )

        soft_reason = reason_code or "backtest_no_trade"
        return RiskEvaluationResult(
            passed=True,
            decision=RiskDecision.WARN if reason_code in self.BACKTEST_SOFT_NO_TRADE_REASON_CODES else RiskDecision.PASS,
            checks=[
                RiskCheckResult(
                    rule_id=f"backtest_signal_{soft_reason}",
                    passed=True,
                    severity=RiskSeverity.WARN if reason_code in {MIN_CONFIDENCE_NOT_MET, TARGET_DELTA_TOO_SMALL} else RiskSeverity.INFO,
                    suggested_action="wait_for_signal" if reason_code in self.BACKTEST_SOFT_NO_TRADE_REASON_CODES else "continue",
                    explanation=explanation,
                    threshold=requested_shares_delta,
                    actual=shares_delta,
                    metadata={"reason_code": reason_code},
                    rule_version=risk_rule_version,
                )
            ],
            rejection_reason=None,
            risk_rule_version=risk_rule_version,
        )

    def _current_risk_rule_version(self, db, user_id: int | None) -> str:
        return self.preference_service.risk_rule_version(db=db, user_id=user_id).version

    @staticmethod
    def _no_trade_reason(
        *,
        action: str,
        shares: int,
        shares_delta: int,
        raw_target_pct: float,
        target_pct: float,
        delta_value: float,
        close_price: float,
        trigger_reason: str,
        block_reason: str | None = None,
    ) -> str | None:
        if shares_delta != 0:
            return None
        if block_reason:
            return block_reason
        if action == "hold":
            if trigger_reason == "min_confidence_not_met":
                return "min_confidence_not_met"
            if raw_target_pct <= 0:
                return MODEL_HOLD_OR_ZERO_TARGET
            return HOLD_SIGNAL
        if action == "buy":
            if target_pct <= 0:
                return ZERO_TARGET_POSITION
            if delta_value <= close_price:
                return TARGET_DELTA_TOO_SMALL
            return INSUFFICIENT_CASH_OR_LOT
        if action in {"sell", "reduce"} and shares <= 0:
            return NO_POSITION_TO_EXIT
        return NO_REBALANCE_NEEDED

    @staticmethod
    def _build_diagnostics(events: list[dict[str, Any]], trades: list[dict[str, Any]]) -> dict[str, Any]:
        signal_counts: dict[str, int] = {}
        rl_action_counts: dict[str, int] = {}
        no_trade_reason_counts: dict[str, int] = {}
        no_trade_samples: list[dict[str, Any]] = []

        for event in events:
            signal = str(event.get("signal") or "unknown")
            signal_counts[signal] = signal_counts.get(signal, 0) + 1

            rl_action = event.get("rl_action_type")
            if rl_action:
                key = str(rl_action)
                rl_action_counts[key] = rl_action_counts.get(key, 0) + 1

            reason = event.get("no_trade_reason")
            if reason:
                key = str(reason)
                no_trade_reason_counts[key] = no_trade_reason_counts.get(key, 0) + 1
                if len(no_trade_samples) < 5:
                    no_trade_samples.append({
                        "trade_date": event.get("trade_date"),
                        "signal": signal,
                        "trigger_reason": event.get("trigger_reason"),
                        "rl_action_type": event.get("rl_action_type"),
                        "target_position_pct": event.get("target_position_pct"),
                        "raw_target_position_pct": event.get("raw_target_position_pct"),
                        "reason": key,
                    })

        return {
            "signal_counts": signal_counts,
            "rl_action_counts": rl_action_counts,
            "no_trade_reason_counts": no_trade_reason_counts,
            "no_trade_samples": no_trade_samples,
            "zero_trade": len(trades) == 0,
        }

    @staticmethod
    def _public_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in parameters.items()
            if key != "model_registry_root"
        }

    @staticmethod
    def _merge_execution_parameters(
        parameters: dict[str, Any] | None,
        *,
        limit_move_policy: dict[str, Any] | None,
        fixed_slippage_amount: float | None,
    ) -> dict[str, Any]:
        merged = dict(parameters or {})
        if limit_move_policy is not None:
            merged["limit_move_policy"] = dict(limit_move_policy)
        if fixed_slippage_amount is not None:
            merged["fixed_slippage_amount"] = float(fixed_slippage_amount)
        return merged

    @staticmethod
    def _max_affordable_buy_shares(
        *,
        cash: float,
        price: float,
        lot_size: int,
        commission_rate: float,
        min_commission: float,
        stamp_tax_rate: float,
    ) -> int:
        if cash <= 0 or price <= 0:
            return 0
        candidate = round_lot_shares(int(cash / price), lot_size=lot_size)
        while candidate > 0:
            cost = calculate_execution_cost(
                quantity=candidate,
                price=price,
                side="buy",
                commission_rate=commission_rate,
                min_commission=min_commission,
                stamp_tax_rate=stamp_tax_rate,
            )
            total_outlay = float(cost.trade_value + cost.total_fee)
            if total_outlay <= cash + 1e-9:
                return candidate
            candidate = max(candidate - lot_size, 0)
        return 0

    def run_portfolio_backtest(
        self,
        db,
        *,
        symbols: list[str],
        weights: list[float] | None = None,
        strategy_id: int | None = None,
        strategy_type: str = "moving_average",
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        initial_cash: float = 100000.0,
        commission_rate: float = 0.0003,
        min_commission: float = 5.0,
        stamp_tax_rate: float = 0.0005,
        slippage_rate: float = 0.0002,
        fixed_slippage_amount: float = 0.0,
        max_position_pct: float = 1.0,
        parameters: dict[str, Any] | None = None,
        limit_move_policy: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        user_id: int | None = None,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        normalized_symbols = [normalize_a_share_symbol(symbol) for symbol in symbols]
        normalized_symbols = [symbol for symbol in normalized_symbols if symbol]
        if not normalized_symbols:
            raise ValueError("symbols must not be empty")
        parameters = self._merge_execution_parameters(parameters, limit_move_policy=limit_move_policy, fixed_slippage_amount=fixed_slippage_amount)
        normalized_weights = self._normalize_weights(weights, len(normalized_symbols))

        child_results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        total = len(normalized_symbols) + 2
        self._emit_progress(progress_callback, 1, total, "准备组合回测", [f"标的数：{len(normalized_symbols)}"])
        for index, (symbol, weight) in enumerate(zip(normalized_symbols, normalized_weights), start=2):
            allocated_cash = initial_cash * weight
            try:
                result = self.run_single_symbol_backtest(
                    db,
                    symbol=symbol,
                    strategy_id=strategy_id,
                    strategy_type=strategy_type,
                    start_date=start_date,
                    end_date=end_date,
                    source=source,
                    adjustflag=adjustflag,
                    initial_cash=allocated_cash,
                    commission_rate=commission_rate,
                    min_commission=min_commission,
                    stamp_tax_rate=stamp_tax_rate,
                    slippage_rate=slippage_rate,
                    fixed_slippage_amount=fixed_slippage_amount,
                    max_position_pct=max_position_pct,
                    parameters=parameters,
                    limit_move_policy=limit_move_policy,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                result["portfolio_weight"] = round(weight, 8)
                child_results.append(result)
            except Exception as error:
                failures.append({"symbol": symbol, "weight": round(weight, 8), "error": str(error)})
            self._emit_progress(progress_callback, index, total, "执行子回测", [f"{symbol} 权重 {weight:.2%}"])

        if not child_results:
            raise ValueError("all portfolio backtests failed")

        equity_curve = self._combine_portfolio_equity(child_results, initial_cash)
        final_net_worth = float(equity_curve[-1]["net_worth"]) if equity_curve else initial_cash
        total_return_pct = 0.0 if initial_cash <= 0 else (final_net_worth - initial_cash) / initial_cash * 100
        max_drawdown_pct = max((float(row.get("drawdown_pct") or 0.0) for row in equity_curve), default=0.0)
        trades = self._prefix_child_rows(child_results, "trades")
        events = self._prefix_child_rows(child_results, "events")
        report = self._build_report(equity_curve=equity_curve, trades=trades, initial_cash=initial_cash, total_fees=sum(float((item.get("summary") or {}).get("total_fees") or 0.0) for item in child_results))
        contributions = self._build_portfolio_contributions(child_results)
        diagnostics = self._build_portfolio_diagnostics(normalized_symbols, normalized_weights, child_results, failures)
        strategy_name = next((item.get("strategy_name") for item in child_results if item.get("strategy_name")), None)
        resolved_strategy_type = str(child_results[0].get("strategy_type") or strategy_type)
        self._emit_progress(progress_callback, total, total, "组合回测完成", [f"组合收益 {total_return_pct:.2f}%"])
        return {
            "status": "completed" if not failures else "partial",
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "strategy_type": resolved_strategy_type,
            "symbols": normalized_symbols,
            "weights": [round(weight, 8) for weight in normalized_weights],
            "source": source,
            "adjustflag": adjustflag,
            "bars": len(equity_curve),
            "initial_cash": initial_cash,
            "final_net_worth": round(final_net_worth, 4),
            "total_return_pct": round(total_return_pct, 6),
            "max_drawdown_pct": round(max_drawdown_pct, 6),
            "trade_count": len(trades),
            "equity_curve": equity_curve,
            "trades": trades,
            "events": events,
            "summary": {
                "result_type": "portfolio_backtest",
                "parameters": self._public_parameters(parameters or {}),
                "risk_rule_version": child_results[0].get("summary", {}).get("risk_rule_version"),
                "weight_summary": {symbol: round(weight, 8) for symbol, weight in zip(normalized_symbols, normalized_weights)},
                "contributions": contributions,
                "diagnostics": diagnostics,
                "report": report,
                "child_results": [self._summarize_child_result(item) for item in child_results],
            },
        }

    def run_parameter_optimization(
        self,
        db,
        *,
        symbol: str,
        strategy_id: int | None = None,
        strategy_type: str = "moving_average",
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        initial_cash: float = 100000.0,
        commission_rate: float = 0.0003,
        min_commission: float = 5.0,
        stamp_tax_rate: float = 0.0005,
        slippage_rate: float = 0.0002,
        fixed_slippage_amount: float = 0.0,
        max_position_pct: float = 1.0,
        parameters: dict[str, Any] | None = None,
        limit_move_policy: dict[str, Any] | None = None,
        parameter_grid: dict[str, list[Any]] | None = None,
        target_metric: str = "total_return_pct",
        sort_direction: str = "desc",
        out_of_sample: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        user_id: int | None = None,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        normalized_symbol = normalize_a_share_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("invalid symbol")
        grid = parameter_grid or {}
        combinations = self._grid_combinations(grid)
        if not combinations:
            raise ValueError("parameter_grid must not be empty")
        if len(combinations) > 30:
            raise ValueError("parameter_grid combinations must be <= 30")

        base_parameters = dict(parameters or {})
        base_parameters = self._merge_execution_parameters(base_parameters, limit_move_policy=limit_move_policy, fixed_slippage_amount=fixed_slippage_amount)
        candidates: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        total = len(combinations) + (1 if out_of_sample else 0)
        for index, candidate_parameters in enumerate(combinations, start=1):
            merged_parameters = {**base_parameters, **candidate_parameters}
            try:
                result = self.run_single_symbol_backtest(
                    db,
                    symbol=normalized_symbol,
                    strategy_id=strategy_id,
                    strategy_type=strategy_type,
                    start_date=start_date,
                    end_date=end_date,
                    source=source,
                    adjustflag=adjustflag,
                    initial_cash=initial_cash,
                    commission_rate=commission_rate,
                    min_commission=min_commission,
                    stamp_tax_rate=stamp_tax_rate,
                    slippage_rate=slippage_rate,
                    fixed_slippage_amount=fixed_slippage_amount,
                    max_position_pct=max_position_pct,
                    parameters=merged_parameters,
                    limit_move_policy=limit_move_policy,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                metric_value = self._metric_value(result, target_metric)
                candidates.append({
                    "rank": 0,
                    "parameters": candidate_parameters,
                    "merged_parameters": self._public_parameters(merged_parameters),
                    "metric_value": metric_value,
                    "metrics": self._optimization_metrics(result),
                    "bars": result.get("bars", 0),
                    "trade_count": result.get("trade_count", 0),
                    "status": result.get("status", "completed"),
                })
            except Exception as error:
                failures.append({"parameters": candidate_parameters, "error": str(error)})
            self._emit_progress(progress_callback, index, max(total, 1), "参数扫描中", [f"组合 {index}/{len(combinations)}"])

        reverse = sort_direction != "asc"
        candidates.sort(key=lambda item: float(item.get("metric_value") or 0.0), reverse=reverse)
        for rank, candidate in enumerate(candidates, start=1):
            candidate["rank"] = rank
        best_candidate = candidates[0] if candidates else None
        oos_result: dict[str, Any] | None = None
        if best_candidate and out_of_sample:
            oos_parameters = dict(best_candidate.get("merged_parameters") or {})
            oos_start = out_of_sample.get("start_date")
            oos_end = out_of_sample.get("end_date")
            result = self.run_single_symbol_backtest(
                db,
                symbol=normalized_symbol,
                strategy_id=strategy_id,
                strategy_type=strategy_type,
                start_date=oos_start,
                end_date=oos_end,
                source=source,
                adjustflag=adjustflag,
                initial_cash=initial_cash,
                commission_rate=commission_rate,
                min_commission=min_commission,
                stamp_tax_rate=stamp_tax_rate,
                slippage_rate=slippage_rate,
                fixed_slippage_amount=fixed_slippage_amount,
                max_position_pct=max_position_pct,
                parameters=oos_parameters,
                limit_move_policy=limit_move_policy,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            oos_result = {
                "start_date": str(oos_start) if oos_start else None,
                "end_date": str(oos_end) if oos_end else None,
                "parameters": oos_parameters,
                "metrics": self._optimization_metrics(result),
                "target_metric_value": self._metric_value(result, target_metric),
                "result": self._summarize_child_result(result),
            }
            self._emit_progress(progress_callback, total, max(total, 1), "样本外验证完成", [f"{target_metric}: {oos_result['target_metric_value']:.4f}"])

        strategy_name = best_candidate.get("strategy_name") if isinstance(best_candidate, dict) else None
        return {
            "status": "completed" if candidates else "failed",
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "strategy_type": strategy_type,
            "symbol": normalized_symbol,
            "source": source,
            "adjustflag": adjustflag,
            "target_metric": target_metric,
            "sort_direction": sort_direction,
            "bars": max((int(candidate.get("bars") or 0) for candidate in candidates), default=0),
            "parameter_grid": grid,
            "combinations": len(combinations),
            "candidates": candidates,
            "matrix": candidates + [{"status": "failed", **failure} for failure in failures],
            "best_candidate": best_candidate,
            "out_of_sample": oos_result,
            "summary": {
                "result_type": "optimization",
                "base_parameters": self._public_parameters(base_parameters),
                "risk_rule_version": best_candidate.get("summary", {}).get("risk_rule_version") if isinstance(best_candidate, dict) else None,
                "failed_count": len(failures),
                "failures": failures,
                "warning": "参数扫描结果可能过拟合，建议参考样本外验证后再人工调整策略参数。",
            },
        }

    @staticmethod
    def _normalize_weights(weights: list[float] | None, count: int) -> list[float]:
        if count <= 0:
            raise ValueError("symbols must not be empty")
        if weights is None:
            return [1.0 / count for _ in range(count)]
        if len(weights) != count:
            raise ValueError("weights length must match symbols")
        if any(weight <= 0 for weight in weights):
            raise ValueError("weights must be positive")
        total = sum(weights)
        if total <= 0:
            raise ValueError("weights sum must be positive")
        return [weight / total for weight in weights]

    @staticmethod
    def _combine_portfolio_equity(results: list[dict[str, Any]], initial_cash: float) -> list[dict[str, Any]]:
        by_symbol: dict[str, dict[str, dict[str, Any]]] = {}
        all_dates: set[str] = set()
        last_values: dict[str, float] = {}
        for result in results:
            symbol = str(result.get("symbol") or "")
            rows = {str(row.get("trade_date") or row.get("date")): row for row in result.get("equity_curve") or [] if row.get("trade_date") or row.get("date")}
            by_symbol[symbol] = rows
            all_dates.update(rows.keys())
            last_values[symbol] = float(result.get("initial_cash") or 0.0)

        equity_curve: list[dict[str, Any]] = []
        peak = initial_cash
        for trade_date in sorted(all_dates):
            components: dict[str, float] = {}
            total_equity = 0.0
            for symbol, rows in by_symbol.items():
                if trade_date in rows:
                    last_values[symbol] = float(rows[trade_date].get("net_worth") or rows[trade_date].get("total_equity") or last_values.get(symbol) or 0.0)
                components[symbol] = round(last_values.get(symbol, 0.0), 4)
                total_equity += last_values.get(symbol, 0.0)
            peak = max(peak, total_equity)
            drawdown_pct = 0.0 if peak <= 0 else (peak - total_equity) / peak * 100
            equity_curve.append({
                "trade_date": trade_date,
                "net_worth": round(total_equity, 4),
                "cash": 0.0,
                "position_value": round(total_equity, 4),
                "position_pct": 1.0,
                "drawdown_pct": round(drawdown_pct, 6),
                "turnover_pct": 0.0,
                "components": components,
            })
        return equity_curve

    @staticmethod
    def _prefix_child_rows(results: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for result in results:
            symbol = str(result.get("symbol") or "")
            weight = float(result.get("portfolio_weight") or 0.0)
            for row in result.get(key) or []:
                item = dict(row)
                item["symbol"] = symbol
                item["portfolio_weight"] = round(weight, 8)
                rows.append(item)
        rows.sort(key=lambda item: str(item.get("trade_date") or ""))
        return rows

    @staticmethod
    def _build_portfolio_contributions(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contributions: list[dict[str, Any]] = []
        for result in results:
            initial_cash = float(result.get("initial_cash") or 0.0)
            final_net_worth = float(result.get("final_net_worth") or initial_cash)
            pnl = final_net_worth - initial_cash
            contributions.append({
                "symbol": result.get("symbol"),
                "weight": round(float(result.get("portfolio_weight") or 0.0), 8),
                "initial_cash": round(initial_cash, 4),
                "final_net_worth": round(final_net_worth, 4),
                "pnl": round(pnl, 4),
                "total_return_pct": result.get("total_return_pct", 0.0),
                "max_drawdown_pct": result.get("max_drawdown_pct", 0.0),
                "trade_count": result.get("trade_count", 0),
            })
        return contributions

    @staticmethod
    def _build_portfolio_diagnostics(symbols: list[str], weights: list[float], results: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
        result_by_symbol = {str(result.get("symbol") or ""): result for result in results}
        missing_symbols = [symbol for symbol in symbols if symbol not in result_by_symbol]
        date_counts = {
            str(result.get("symbol") or ""): len(result.get("equity_curve") or [])
            for result in results
        }
        return {
            "requested_symbols": symbols,
            "normalized_weights": {symbol: round(weight, 8) for symbol, weight in zip(symbols, weights)},
            "missing_symbols": missing_symbols,
            "date_counts": date_counts,
            "failures": failures,
            "has_data_gap": bool(missing_symbols or failures or len(set(date_counts.values())) > 1),
        }

    @staticmethod
    def _summarize_child_result(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": result.get("status"),
            "symbol": result.get("symbol"),
            "strategy_id": result.get("strategy_id"),
            "strategy_name": result.get("strategy_name"),
            "strategy_type": result.get("strategy_type"),
            "bars": result.get("bars", 0),
            "initial_cash": result.get("initial_cash", 0.0),
            "final_net_worth": result.get("final_net_worth", 0.0),
            "total_return_pct": result.get("total_return_pct", 0.0),
            "max_drawdown_pct": result.get("max_drawdown_pct", 0.0),
            "trade_count": result.get("trade_count", 0),
            "report": (result.get("summary") or {}).get("report") if isinstance(result.get("summary"), dict) else {},
        }

    @staticmethod
    def _grid_combinations(parameter_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
        keys = list(parameter_grid.keys())
        if not keys:
            return []
        value_lists = [parameter_grid[key] for key in keys]
        if any(not values for values in value_lists):
            return []
        return [dict(zip(keys, values)) for values in product(*value_lists)]

    @staticmethod
    def _metric_value(result: dict[str, Any], target_metric: str) -> float:
        if target_metric in result:
            return float(result.get(target_metric) or 0.0)
        report = (result.get("summary") or {}).get("report") if isinstance(result.get("summary"), dict) else {}
        if isinstance(report, dict) and target_metric in report:
            return float(report.get(target_metric) or 0.0)
        return 0.0

    @staticmethod
    def _optimization_metrics(result: dict[str, Any]) -> dict[str, Any]:
        report = (result.get("summary") or {}).get("report") if isinstance(result.get("summary"), dict) else {}
        report = report if isinstance(report, dict) else {}
        return {
            "total_return_pct": result.get("total_return_pct", 0.0),
            "max_drawdown_pct": result.get("max_drawdown_pct", 0.0),
            "sharpe_ratio": report.get("sharpe_ratio", 0.0),
            "final_net_worth": result.get("final_net_worth", 0.0),
            "trade_count": result.get("trade_count", 0),
        }

    def build_daily_review(self, db, **kwargs: Any) -> dict[str, Any]:
        backtest = self.run_single_symbol_backtest(db, **kwargs)
        review_date = backtest.get("summary", {}).get("last_trade_date")
        if backtest["status"] != "completed":
            review = {
                "status": "empty",
                "review_date": review_date,
                "headline": "暂无可复盘的回测数据",
                "backtest": backtest,
                "highlights": [],
                "risks": ["历史数据为空，无法生成收盘复盘"],
                "next_actions": ["先同步该标的历史日线数据"],
            }
            self._archive_daily_review(db, review, kwargs)
            return review

        report = backtest.get("summary", {}).get("report", {})
        total_return_pct = float(backtest.get("total_return_pct", 0.0))
        max_drawdown_pct = float(backtest.get("max_drawdown_pct", 0.0))
        trade_count = int(backtest.get("trade_count", 0))
        win_rate_pct = float(report.get("win_rate_pct", 0.0))
        headline = "回测收盘复盘：策略阶段性跑赢初始资金" if total_return_pct >= 0 else "回测收盘复盘：策略阶段性承压"
        highlights = [
            f"累计收益率 {total_return_pct:.2f}%",
            f"交易 {trade_count} 笔，胜率 {win_rate_pct:.2f}%",
            f"最终净值 {float(backtest.get('final_net_worth', 0.0)):.2f}",
        ]
        risks = [f"最大回撤 {max_drawdown_pct:.2f}%"]
        if trade_count == 0:
            risks.append("回测期间未触发交易，策略信号可能过于保守或样本不足")
        if max_drawdown_pct > 10:
            risks.append("回撤超过 10%，需要复核仓位与止损参数")
        next_actions = [
            "扩大历史样本窗口，确认参数稳定性",
            "对比至少一个基准策略或买入持有表现",
            "若用于自动交易，先保持 signal_only 观察",
        ]
        review = {
            "status": "completed",
            "review_date": review_date,
            "headline": headline,
            "backtest": backtest,
            "highlights": highlights,
            "risks": risks,
            "next_actions": next_actions,
        }
        self._archive_daily_review(db, review, kwargs)
        return review

    @staticmethod
    def _archive_daily_review(db, review: dict[str, Any], request: dict[str, Any]) -> None:
        backtest = review.get("backtest") if isinstance(review.get("backtest"), dict) else {}
        summary = {
            "status": backtest.get("status"),
            "strategy_id": backtest.get("strategy_id"),
            "strategy_name": backtest.get("strategy_name"),
            "strategy_type": backtest.get("strategy_type"),
            "symbol": backtest.get("symbol"),
            "bars": backtest.get("bars"),
            "total_return_pct": backtest.get("total_return_pct"),
            "max_drawdown_pct": backtest.get("max_drawdown_pct"),
            "trade_count": backtest.get("trade_count"),
            "final_net_worth": backtest.get("final_net_worth"),
            "report": (backtest.get("summary") or {}).get("report") if isinstance(backtest.get("summary"), dict) else {},
        }
        review_date = BacktestService._coerce_review_date(review.get("review_date"))
        item = DailyReview(
            tenant_id=str(request.get("tenant_id") or "local"),
            user_id=request.get("user_id"),
            review_date=review_date,
            symbol=str(backtest.get("symbol") or request.get("symbol") or ""),
            strategy_id=backtest.get("strategy_id"),
            strategy_name=backtest.get("strategy_name"),
            strategy_type=str(backtest.get("strategy_type") or request.get("strategy_type") or ""),
            headline=str(review.get("headline") or ""),
            highlights=list(review.get("highlights") or []),
            risks=list(review.get("risks") or []),
            next_actions=list(review.get("next_actions") or []),
            backtest_summary=summary,
            payload=review,
        )
        db.add(item)
        db.commit()

    @staticmethod
    def _coerce_review_date(value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str) and value:
            return date.fromisoformat(value)
        return None

    @staticmethod
    def _build_report(
        *,
        equity_curve: list[dict[str, Any]],
        trades: list[dict[str, Any]],
        initial_cash: float,
        total_fees: float,
    ) -> dict[str, Any]:
        returns: list[float] = []
        previous_net_worth = initial_cash
        for row in equity_curve:
            net_worth = float(row["net_worth"])
            returns.append(0.0 if previous_net_worth <= 0 else (net_worth - previous_net_worth) / previous_net_worth)
            previous_net_worth = net_worth

        mean_return = sum(returns) / len(returns) if returns else 0.0
        variance = sum((item - mean_return) ** 2 for item in returns) / len(returns) if returns else 0.0
        volatility = math.sqrt(variance)
        downside_returns = [item for item in returns if item < 0]
        downside_variance = sum(item**2 for item in downside_returns) / len(downside_returns) if downside_returns else 0.0
        downside_volatility = math.sqrt(downside_variance)
        final_net_worth = float(equity_curve[-1]["net_worth"]) if equity_curve else initial_cash
        total_return = 0.0 if initial_cash <= 0 else (final_net_worth - initial_cash) / initial_cash
        annualized_return = ((1 + total_return) ** (252 / max(1, len(returns))) - 1) if total_return > -1 and returns else 0.0
        annualized_volatility = volatility * math.sqrt(252)
        max_drawdown_pct = max((float(row["drawdown_pct"]) for row in equity_curve), default=0.0)
        buy_count = sum(1 for trade in trades if trade.get("side") == "buy")
        sell_count = sum(1 for trade in trades if trade.get("side") == "sell")
        win_rate_pct = sum(1 for item in returns if item > 0) / len(returns) * 100 if returns else 0.0
        return {
            "annualized_return_pct": round(annualized_return * 100, 6),
            "annualized_volatility_pct": round(annualized_volatility * 100, 6),
            "sharpe_ratio": round((mean_return / volatility) * math.sqrt(252), 6) if volatility else 0.0,
            "sortino_ratio": round((mean_return / downside_volatility) * math.sqrt(252), 6) if downside_volatility else 0.0,
            "calmar_ratio": round((annualized_return * 100) / max_drawdown_pct, 6) if max_drawdown_pct else 0.0,
            "win_rate_pct": round(win_rate_pct, 6),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "total_fees": round(total_fees, 4),
            "drawdown_curve": [
                {"trade_date": row["trade_date"], "drawdown_pct": row["drawdown_pct"]}
                for row in equity_curve
            ],
        }
