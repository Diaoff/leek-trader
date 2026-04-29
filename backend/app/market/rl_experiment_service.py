from __future__ import annotations

from datetime import date
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.market.rl_dataset_service import RLDatasetBuilder
from app.quant.actions import RLActionEncoding
from app.quant.simulator import RLEpisodeConfig, RLEpisodeSimulator, RLPolicyName, RLRewardMode
from app.market.symbols import normalize_a_share_symbol


class RLExperimentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def run_single_symbol_experiment(
        self,
        *,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        exclude_suspended: bool = True,
        policy: RLPolicyName = "buy_and_hold",
        initial_cash: float = 100000.0,
        commission_rate: float = 0.0003,
        slippage_rate: float = 0.0002,
        reward_mode: RLRewardMode = "net_worth_change",
        max_position_pct: float = 1.0,
        ma_short_window: int = 5,
        ma_long_window: int = 20,
        drawdown_penalty_coef: float = 0.02,
        turnover_penalty_coef: float = 0.001,
        action_sequence: list[Any] | None = None,
        action_encoding: RLActionEncoding = "legacy_zero_based",
    ) -> dict[str, Any]:
        normalized_symbol = normalize_a_share_symbol(symbol)
        dataset = RLDatasetBuilder(self.db).build_dataset(
            symbols=[normalized_symbol],
            start_date=start_date,
            end_date=end_date,
            source=source,
            adjustflag=adjustflag,
            exclude_suspended=exclude_suspended,
        )
        config = RLEpisodeConfig(
            initial_cash=initial_cash,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            reward_mode=reward_mode,
            max_position_pct=max_position_pct,
            ma_short_window=ma_short_window,
            ma_long_window=ma_long_window,
            drawdown_penalty_coef=drawdown_penalty_coef,
            turnover_penalty_coef=turnover_penalty_coef,
        )
        result = RLEpisodeSimulator(config).simulate(
            dataset.records,
            policy_name=policy,
            action_sequence=action_sequence,
            action_encoding=action_encoding,
        )
        payload = result.to_dict()
        payload["symbol"] = normalized_symbol
        payload["dataset"] = {
            "status": dataset.status,
            "count": dataset.count,
            "manifest": dataset.manifest,
        }
        if dataset.count == 0:
            payload["status"] = "empty"
            payload["summary"] = {**payload.get("summary", {}), "reason": "no_records", "symbol": normalized_symbol}
        return payload

    def run_batch_evaluation(
        self,
        *,
        symbols: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        exclude_suspended: bool = True,
        policy: RLPolicyName = "buy_and_hold",
        initial_cash: float = 100000.0,
        commission_rate: float = 0.0003,
        slippage_rate: float = 0.0002,
        reward_mode: RLRewardMode = "net_worth_change",
        max_position_pct: float = 1.0,
        ma_short_window: int = 5,
        ma_long_window: int = 20,
        drawdown_penalty_coef: float = 0.02,
        turnover_penalty_coef: float = 0.001,
        action_sequence: list[Any] | None = None,
        action_encoding: RLActionEncoding = "legacy_zero_based",
    ) -> dict[str, Any]:
        normalized_symbols = self._normalize_symbols(symbols)
        if not normalized_symbols:
            raise ValueError("symbols must be a non-empty explicit list")

        results: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for symbol in normalized_symbols:
            try:
                result = self.run_single_symbol_experiment(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    source=source,
                    adjustflag=adjustflag,
                    exclude_suspended=exclude_suspended,
                    policy=policy,
                    initial_cash=initial_cash,
                    commission_rate=commission_rate,
                    slippage_rate=slippage_rate,
                    reward_mode=reward_mode,
                    max_position_pct=max_position_pct,
                    ma_short_window=ma_short_window,
                    ma_long_window=ma_long_window,
                    drawdown_penalty_coef=drawdown_penalty_coef,
                    turnover_penalty_coef=turnover_penalty_coef,
                    action_sequence=action_sequence,
                    action_encoding=action_encoding,
                )
                if result["status"] == "completed":
                    results.append(result)
                else:
                    failures.append({"symbol": symbol, "reason": result.get("summary", {}).get("reason", result["status"])})
            except Exception as error:  # noqa: BLE001 - batch evaluation must isolate symbol failures
                failures.append({"symbol": symbol, "reason": str(error)})

        ranking = [
            {
                "symbol": item["symbol"],
                "status": item["status"],
                "total_return_pct": item["total_return_pct"],
                "final_net_worth": item["final_net_worth"],
                "max_drawdown_pct": item["max_drawdown_pct"],
            }
            for item in results
        ]
        ranking.sort(key=lambda item: (-float(item["total_return_pct"]), str(item["symbol"])))
        return {
            "status": "completed" if results else "empty",
            "success_count": len(results),
            "failure_count": len(failures),
            "failures": failures,
            "results": results,
            "ranking": ranking,
        }

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized_symbol = normalize_a_share_symbol(symbol)
            if not normalized_symbol or normalized_symbol in seen:
                continue
            seen.add(normalized_symbol)
            normalized.append(normalized_symbol)
        return normalized
