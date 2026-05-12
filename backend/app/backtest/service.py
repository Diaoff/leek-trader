from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.market.baostock_sync_service import BaoStockHistorySyncService
from app.market.data_service import MarketDataService
from app.market.history_storage import MarketDailyBarStorage
from app.market.providers.base import DailyBarSnapshot
from app.market.symbols import normalize_a_share_symbol
from app.models.strategy import Strategy
from app.models.daily_review import DailyReview
from app.strategy.plugins import StrategyPluginRegistry


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
    def __init__(self) -> None:
        self.strategy_registry = StrategyPluginRegistry()

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
        slippage_rate: float = 0.0002,
        max_position_pct: float = 1.0,
        parameters: dict[str, Any] | None = None,
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
            return BacktestResult(
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
                summary=summary,
            ).to_dict()

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
            slippage_rate=slippage_rate,
            max_position_pct=max_position_pct,
            source=source,
            adjustflag=adjustflag,
        )
        result["strategy_type"] = strategy_type
        result["strategy_id"] = strategy_id
        result["strategy_name"] = strategy_name
        result["symbol"] = normalized_symbol
        result["source"] = source
        result["adjustflag"] = adjustflag
        if sync_summary is not None:
            result.setdefault("summary", {})["history_sync"] = sync_summary
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
        return storage.list_bars(
            symbol=symbol,
            source=source,
            adjustflag=adjustflag,
            start_date=start_date,
            end_date=end_date,
        ).bars

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
        return normalized

    def _simulate_events(
        self,
        *,
        bars: list[DailyBarSnapshot],
        plugin_name: str,
        plugin,
        parameters: dict[str, Any],
        initial_cash: float,
        commission_rate: float,
        slippage_rate: float,
        max_position_pct: float,
        source: str,
        adjustflag: str,
    ) -> dict[str, Any]:
        cash = initial_cash
        shares = 0
        peak = initial_cash
        previous_net_worth = initial_cash
        total_fees = 0.0
        trades: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []

        for index, bar in enumerate(bars):
            history = bars[: index + 1]
            signal = plugin.evaluate(str(bar.symbol), history, parameters)
            action = str(signal.get("signal", "hold"))
            rl_action = signal.get("rl_action") if isinstance(signal.get("rl_action"), dict) else {}
            raw_target_pct = float((rl_action or {}).get("raw_target_position_pct") or signal.get("position_pct") or 0.0)
            trigger_reason = str(signal.get("trigger_reason") or "")
            target_pct = float(signal.get("position_pct") or 0.0)
            if action == "buy":
                target_pct = min(target_pct or 0.1, max_position_pct)
            elif action in {"sell", "reduce"}:
                target_pct = 0.0 if action == "sell" else min(shares * float(bar.close_price) / (cash + shares * float(bar.close_price)) if cash + shares * float(bar.close_price) > 0 else 0.0, max_position_pct)
            else:
                target_pct = shares * float(bar.close_price) / (cash + shares * float(bar.close_price)) if cash + shares * float(bar.close_price) > 0 else 0.0

            close_price = float(bar.close_price)
            execution_price = close_price * (1 + slippage_rate if action == "buy" else 1 - slippage_rate if action in {"sell", "reduce"} else 1)
            net_worth = cash + shares * close_price
            target_value = net_worth * target_pct
            current_value = shares * close_price
            delta_value = target_value - current_value
            shares_delta = 0
            fee = 0.0

            if delta_value > close_price:
                bought = int(delta_value / (execution_price * (1 + commission_rate)))
                affordable = int(cash / (execution_price * (1 + commission_rate)))
                shares_delta = max(0, min(bought, affordable))
                trade_value = shares_delta * execution_price
                fee = trade_value * commission_rate
                cash -= trade_value + fee
                shares += shares_delta
            elif delta_value < -close_price and shares > 0:
                sold = min(shares, int(abs(delta_value) / execution_price))
                shares_delta = -sold
                trade_value = sold * execution_price
                fee = trade_value * commission_rate
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
            )

            total_fees += fee
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
                    "rl_action_type": (rl_action or {}).get("action_type"),
                    "raw_target_position_pct": round(raw_target_pct, 6),
                    "target_position_pct": round(target_pct, 6),
                    "shares_delta": shares_delta,
                    "no_trade_reason": no_trade_reason,
                    "execution_price": round(execution_price, 6),
                }
            )
            if shares_delta != 0:
                trades.append(
                    {
                        "trade_date": str(bar.trade_date),
                        "side": "buy" if shares_delta > 0 else "sell",
                        "shares_delta": shares_delta,
                        "execution_price": round(execution_price, 6),
                        "fee": round(fee, 4),
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
        return BacktestResult(
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
                "total_fees": round(total_fees, 4),
                "first_trade_date": str(bars[0].trade_date),
                "last_trade_date": str(bars[-1].trade_date),
                "diagnostics": diagnostics,
                "report": report,
            },
        ).to_dict()

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
    ) -> str | None:
        if shares_delta != 0:
            return None
        if action == "hold":
            if trigger_reason == "min_confidence_not_met":
                return "min_confidence_not_met"
            if raw_target_pct <= 0:
                return "model_hold_or_zero_target"
            return "hold_signal"
        if action == "buy":
            if target_pct <= 0:
                return "zero_target_position"
            if delta_value <= close_price:
                return "target_delta_too_small"
            return "insufficient_cash_or_lot"
        if action in {"sell", "reduce"} and shares <= 0:
            return "no_position_to_exit"
        return "no_rebalance_needed"

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
