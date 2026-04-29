from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.quant.actions import RLAction, RLActionDecoder, RLActionEncoding, RLActionType
from app.quant.features import RL_FACTOR_FIELDS, RL_LIQUIDITY_FIELDS, RL_PRICE_FIELDS

RLPolicyName = Literal["buy_and_hold", "moving_average", "cash", "action_replay"]
RLRewardMode = Literal["net_worth_change", "excess_return", "drawdown_penalty", "risk_adjusted_excess_return"]


@dataclass(slots=True)
class RLEpisodeConfig:
    initial_cash: float = 100000.0
    commission_rate: float = 0.0003
    slippage_rate: float = 0.0002
    reward_mode: RLRewardMode = "net_worth_change"
    max_position_pct: float = 1.0
    ma_short_window: int = 5
    ma_long_window: int = 20
    drawdown_penalty_coef: float = 0.02
    turnover_penalty_coef: float = 0.001


@dataclass(slots=True)
class RLEpisodeStep:
    step: int
    symbol: str
    trade_date: str
    close_price: float
    action_type: RLActionType
    target_position_pct: float
    shares: int
    cash: float
    position_value: float
    net_worth: float
    reward: float
    benchmark_return: float
    drawdown_pct: float
    fee: float
    observation: dict[str, Any]


@dataclass(slots=True)
class RLEpisodeResult:
    status: str
    policy: RLPolicyName
    reward_mode: RLRewardMode
    initial_cash: float
    final_net_worth: float
    total_return_pct: float
    max_drawdown_pct: float
    total_reward: float
    total_fees: float
    steps: list[RLEpisodeStep] = field(default_factory=list)
    feature_groups: dict[str, list[str]] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    rewards: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "policy": self.policy,
            "reward_mode": self.reward_mode,
            "initial_cash": self.initial_cash,
            "final_net_worth": self.final_net_worth,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_reward": self.total_reward,
            "total_fees": self.total_fees,
            "feature_groups": self.feature_groups,
            "summary": self.summary,
            "equity_curve": self.equity_curve,
            "actions": self.actions,
            "positions": self.positions,
            "rewards": self.rewards,
            "steps": [
                {
                    "step": item.step,
                    "symbol": item.symbol,
                    "trade_date": item.trade_date,
                    "close_price": item.close_price,
                    "action_type": item.action_type,
                    "target_position_pct": item.target_position_pct,
                    "shares": item.shares,
                    "cash": item.cash,
                    "position_value": item.position_value,
                    "net_worth": item.net_worth,
                    "reward": item.reward,
                    "benchmark_return": item.benchmark_return,
                    "drawdown_pct": item.drawdown_pct,
                    "fee": item.fee,
                    "observation": item.observation,
                }
                for item in self.steps
            ],
        }



class BaselinePolicy:
    def __init__(self, name: RLPolicyName, *, ma_short_window: int = 5, ma_long_window: int = 20) -> None:
        self.name = name
        self.ma_short_window = ma_short_window
        self.ma_long_window = ma_long_window

    def action_for(self, records: list[dict[str, Any]], index: int) -> RLAction:
        if self.name == "cash":
            return RLAction("hold", 0.0)
        if self.name == "buy_and_hold":
            return RLAction("buy", 1.0)
        return self._moving_average_action(records, index)

    def _moving_average_action(self, records: list[dict[str, Any]], index: int) -> RLAction:
        if index + 1 < self.ma_long_window:
            return RLAction("hold", 0.0)
        closes = [float(record["close_price"]) for record in records]
        short_avg = sum(closes[index + 1 - self.ma_short_window : index + 1]) / self.ma_short_window
        long_avg = sum(closes[index + 1 - self.ma_long_window : index + 1]) / self.ma_long_window
        if short_avg > long_avg:
            return RLAction("buy", 1.0)
        if short_avg < long_avg:
            return RLAction("sell", 0.0)
        return RLAction("hold", 0.0)


class RewardCalculator:
    def __init__(self, mode: RLRewardMode) -> None:
        self.mode = mode

    def calculate(
        self,
        *,
        net_worth: float,
        previous_net_worth: float,
        benchmark_return: float,
        drawdown_pct: float,
        turnover_pct: float = 0.0,
        cost_pct: float = 0.0,
        drawdown_penalty_coef: float = 0.02,
        turnover_penalty_coef: float = 0.001,
    ) -> float:
        portfolio_return = 0.0 if previous_net_worth <= 0 else (net_worth - previous_net_worth) / previous_net_worth
        if self.mode == "risk_adjusted_excess_return":
            return portfolio_return - benchmark_return - max(0.0, drawdown_pct) * 0.01 * drawdown_penalty_coef - max(0.0, turnover_pct) * turnover_penalty_coef - max(0.0, cost_pct)
        if self.mode == "excess_return":
            return portfolio_return - benchmark_return
        if self.mode == "drawdown_penalty":
            return portfolio_return - max(0.0, drawdown_pct) * 0.01
        return portfolio_return


class RLEpisodeSimulator:
    def __init__(self, config: RLEpisodeConfig | None = None) -> None:
        self.config = config or RLEpisodeConfig()

    def simulate(
        self,
        records: list[dict[str, Any]],
        *,
        policy_name: RLPolicyName = "buy_and_hold",
        action_sequence: list[Any] | None = None,
        action_encoding: RLActionEncoding = "legacy_zero_based",
    ) -> RLEpisodeResult:
        normalized_records = self._normalize_records(records)
        if not normalized_records:
            return RLEpisodeResult(
                status="empty",
                policy=policy_name,
                reward_mode=self.config.reward_mode,
                initial_cash=self.config.initial_cash,
                final_net_worth=self.config.initial_cash,
                total_return_pct=0.0,
                max_drawdown_pct=0.0,
                total_reward=0.0,
                total_fees=0.0,
                feature_groups=self.feature_groups(),
                summary={"reason": "no_records"},
            )

        replay_actions = self._build_replay_actions(action_sequence or [], action_encoding=action_encoding)
        effective_policy: RLPolicyName = "action_replay" if replay_actions else policy_name
        policy = BaselinePolicy(policy_name, ma_short_window=self.config.ma_short_window, ma_long_window=self.config.ma_long_window)
        reward_calculator = RewardCalculator(self.config.reward_mode)
        cash = self.config.initial_cash
        shares = 0
        first_close = float(normalized_records[0]["close_price"])
        previous_close = first_close
        previous_net_worth = self.config.initial_cash
        peak_net_worth = self.config.initial_cash
        total_reward = 0.0
        total_fees = 0.0
        steps: list[RLEpisodeStep] = []
        equity_curve: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        positions: list[dict[str, Any]] = []
        rewards: list[dict[str, Any]] = []
        cost_basis = 0.0

        for index, record in enumerate(normalized_records):
            close_price = float(record["close_price"])
            action = self._replay_action_for(replay_actions, record, index) or policy.action_for(normalized_records, index)
            target_pct = min(action.target_position_pct, self.config.max_position_pct)
            if action.action_type == "hold":
                target_pct = self._current_position_pct(cash, shares, close_price)
            previous_shares = shares
            cash, shares, fee, shares_delta, execution_price = self._rebalance(
                cash=cash,
                shares=shares,
                price=close_price,
                target_position_pct=target_pct,
            )
            if shares_delta > 0:
                cost_basis = ((cost_basis * previous_shares) + (shares_delta * execution_price)) / shares if shares else 0.0
            elif shares == 0:
                cost_basis = 0.0
            total_fees += fee
            position_value = shares * close_price
            net_worth = cash + position_value
            peak_net_worth = max(peak_net_worth, net_worth)
            drawdown_pct = 0.0 if peak_net_worth <= 0 else (peak_net_worth - net_worth) / peak_net_worth * 100
            benchmark_return = 0.0 if index == 0 or previous_close <= 0 else (close_price - previous_close) / previous_close
            traded_value = abs(shares_delta) * execution_price
            turnover_pct = 0.0 if previous_net_worth <= 0 else traded_value / previous_net_worth
            cost_pct = 0.0 if previous_net_worth <= 0 else fee / previous_net_worth
            reward = reward_calculator.calculate(
                net_worth=net_worth,
                previous_net_worth=previous_net_worth,
                benchmark_return=benchmark_return,
                drawdown_pct=drawdown_pct,
                turnover_pct=turnover_pct,
                cost_pct=cost_pct,
                drawdown_penalty_coef=self.config.drawdown_penalty_coef,
                turnover_penalty_coef=self.config.turnover_penalty_coef,
            )
            total_reward += reward
            portfolio_return = 0.0 if previous_net_worth <= 0 else (net_worth - previous_net_worth) / previous_net_worth
            trade_date = str(record["trade_date"])
            position_pct = round(position_value / net_worth, 6) if net_worth else 0.0
            equity_curve.append(
                {
                    "trade_date": trade_date,
                    "net_worth": round(net_worth, 4),
                    "cash": round(cash, 4),
                    "position_value": round(position_value, 4),
                    "drawdown_pct": round(drawdown_pct, 6),
                    "benchmark_return": round(benchmark_return, 10),
                    "drawdown_penalty": round(max(0.0, drawdown_pct) * 0.01 * self.config.drawdown_penalty_coef, 10),
                    "turnover_penalty": round(max(0.0, turnover_pct) * self.config.turnover_penalty_coef + max(0.0, cost_pct), 10),
                }
            )
            actions.append(
                {
                    "trade_date": trade_date,
                    "action_type": action.action_type,
                    "target_position_pct": round(target_pct, 6),
                    "shares_delta": shares_delta,
                    "fee": round(fee, 4),
                    "execution_price": round(execution_price, 6),
                    "source": "replay" if replay_actions else "policy",
                }
            )
            positions.append(
                {
                    "trade_date": trade_date,
                    "shares": shares,
                    "position_value": round(position_value, 4),
                    "position_pct": position_pct,
                    "cost_basis": round(cost_basis, 6),
                }
            )
            rewards.append(
                {
                    "trade_date": trade_date,
                    "reward": round(reward, 10),
                    "reward_mode": self.config.reward_mode,
                    "portfolio_return": round(portfolio_return, 10),
                    "benchmark_return": round(benchmark_return, 10),
                }
            )
            steps.append(
                RLEpisodeStep(
                    step=index,
                    symbol=str(record["symbol"]),
                    trade_date=str(record["trade_date"]),
                    close_price=close_price,
                    action_type=action.action_type,
                    target_position_pct=round(target_pct, 6),
                    shares=shares,
                    cash=round(cash, 4),
                    position_value=round(position_value, 4),
                    net_worth=round(net_worth, 4),
                    reward=round(reward, 10),
                    benchmark_return=round(benchmark_return, 10),
                    drawdown_pct=round(drawdown_pct, 6),
                    fee=round(fee, 4),
                    observation=self._observation(record, cash=cash, shares=shares, net_worth=net_worth, close_price=close_price),
                )
            )
            previous_net_worth = net_worth
            previous_close = close_price

        final_net_worth = steps[-1].net_worth
        risk_metrics = self._risk_metrics(equity_curve=equity_curve, actions=actions)
        return RLEpisodeResult(
            status="completed",
            policy=effective_policy,
            reward_mode=self.config.reward_mode,
            initial_cash=self.config.initial_cash,
            final_net_worth=final_net_worth,
            total_return_pct=round((final_net_worth - self.config.initial_cash) / self.config.initial_cash * 100, 6),
            max_drawdown_pct=max((step.drawdown_pct for step in steps), default=0.0),
            total_reward=round(total_reward, 10),
            total_fees=round(total_fees, 4),
            steps=steps,
            feature_groups=self.feature_groups(),
            equity_curve=equity_curve,
            actions=actions,
            positions=positions,
            rewards=rewards,
            summary={
                "records": len(normalized_records),
                "first_trade_date": normalized_records[0]["trade_date"],
                "last_trade_date": normalized_records[-1]["trade_date"],
                "benchmark_return_pct": round((float(normalized_records[-1]["close_price"]) - first_close) / first_close * 100, 6) if first_close else 0.0,
                "risk_metrics": risk_metrics,
                "action_replay": {
                    "enabled": bool(replay_actions),
                    "provided_actions": len(action_sequence or []),
                    "encoding": action_encoding,
                    "missing_action_count": max(0, len(normalized_records) - len(replay_actions)) if replay_actions else 0,
                },
            },
        )

    @staticmethod
    def _build_replay_actions(action_sequence: list[Any], *, action_encoding: RLActionEncoding) -> list[dict[str, Any]]:
        replay_actions: list[dict[str, Any]] = []
        for index, raw_action in enumerate(action_sequence):
            trade_date = raw_action.get("trade_date") if isinstance(raw_action, dict) else None
            action_payload = raw_action.get("action") if isinstance(raw_action, dict) and "action" in raw_action else raw_action
            decoded = RLActionDecoder.decode(action_payload, encoding=action_encoding)
            replay_actions.append({"index": index, "trade_date": str(trade_date) if trade_date else None, "action": decoded})
        return replay_actions

    @staticmethod
    def _replay_action_for(replay_actions: list[dict[str, Any]], record: dict[str, Any], index: int) -> RLAction | None:
        if not replay_actions:
            return None
        record_date = str(record["trade_date"])
        for replay_action in replay_actions:
            if replay_action["trade_date"] == record_date:
                return replay_action["action"]
        if index < len(replay_actions) and replay_actions[index]["trade_date"] is None:
            return replay_actions[index]["action"]
        return RLAction("hold", 0.0)

    def _risk_metrics(self, *, equity_curve: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, float]:
        if len(equity_curve) < 2:
            return {
                "annualized_return_pct": 0.0,
                "annualized_volatility_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "win_rate_pct": 0.0,
                "turnover_pct": 0.0,
            }
        returns = []
        previous_net_worth = float(equity_curve[0]["net_worth"])
        for point in equity_curve[1:]:
            net_worth = float(point["net_worth"])
            returns.append(0.0 if previous_net_worth <= 0 else (net_worth - previous_net_worth) / previous_net_worth)
            previous_net_worth = net_worth
        mean_return = sum(returns) / len(returns)
        variance = sum((item - mean_return) ** 2 for item in returns) / len(returns)
        volatility = variance**0.5
        total_return = 0.0 if self.config.initial_cash <= 0 else (float(equity_curve[-1]["net_worth"]) - self.config.initial_cash) / self.config.initial_cash
        annualized_return = ((1 + total_return) ** (252 / max(1, len(returns))) - 1) if total_return > -1 else -1.0
        annualized_volatility = volatility * (252**0.5)
        downside_returns = [item for item in returns if item < 0]
        downside_variance = sum(item**2 for item in downside_returns) / len(downside_returns) if downside_returns else 0.0
        downside_volatility = downside_variance**0.5
        max_drawdown_pct = max((float(point["drawdown_pct"]) for point in equity_curve), default=0.0)
        traded_value = sum(abs(float(action["shares_delta"])) * float(action["execution_price"]) for action in actions)
        return {
            "annualized_return_pct": round(annualized_return * 100, 6),
            "annualized_volatility_pct": round(annualized_volatility * 100, 6),
            "sharpe_ratio": round((mean_return / volatility) * (252**0.5), 6) if volatility else 0.0,
            "sortino_ratio": round((mean_return / downside_volatility) * (252**0.5), 6) if downside_volatility else 0.0,
            "calmar_ratio": round((annualized_return * 100) / max_drawdown_pct, 6) if max_drawdown_pct else 0.0,
            "win_rate_pct": round(sum(1 for item in returns if item > 0) / len(returns) * 100, 6),
            "turnover_pct": round(traded_value / self.config.initial_cash * 100, 6) if self.config.initial_cash else 0.0,
        }

    def _rebalance(self, *, cash: float, shares: int, price: float, target_position_pct: float) -> tuple[float, int, float, int, float]:
        if price <= 0:
            return cash, shares, 0.0, 0, price
        net_worth = cash + shares * price
        target_value = net_worth * target_position_pct
        current_value = shares * price
        delta_value = target_value - current_value
        trade_price_buy = price * (1 + self.config.slippage_rate)
        trade_price_sell = price * (1 - self.config.slippage_rate)
        if delta_value > price:
            gross_shares = int(delta_value / trade_price_buy)
            max_affordable = int(cash / (trade_price_buy * (1 + self.config.commission_rate)))
            bought = max(0, min(gross_shares, max_affordable))
            trade_value = bought * trade_price_buy
            fee = trade_value * self.config.commission_rate
            return cash - trade_value - fee, shares + bought, fee, bought, trade_price_buy
        if delta_value < -price and shares > 0:
            sold = min(shares, int(abs(delta_value) / trade_price_sell))
            trade_value = sold * trade_price_sell
            fee = trade_value * self.config.commission_rate
            return cash + trade_value - fee, shares - sold, fee, -sold, trade_price_sell
        return cash, shares, 0.0, 0, price

    @staticmethod
    def _current_position_pct(cash: float, shares: int, price: float) -> float:
        net_worth = cash + shares * price
        if net_worth <= 0:
            return 0.0
        return shares * price / net_worth

    @staticmethod
    def _normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            [record for record in records if record.get("symbol") and record.get("trade_date") and float(record.get("close_price") or 0) > 0],
            key=lambda record: (str(record["symbol"]), str(record["trade_date"])),
        )

    @staticmethod
    def _observation(record: dict[str, Any], *, cash: float, shares: int, net_worth: float, close_price: float) -> dict[str, Any]:
        position_value = shares * close_price
        return {
            "market": {field: record.get(field) for field in [*RL_PRICE_FIELDS, *RL_LIQUIDITY_FIELDS, *RL_FACTOR_FIELDS]},
            "account": {
                "cash": round(cash, 4),
                "shares": shares,
                "position_value": round(position_value, 4),
                "net_worth": round(net_worth, 4),
                "position_pct": round(position_value / net_worth, 6) if net_worth else 0.0,
            },
        }

    @staticmethod
    def feature_groups() -> dict[str, list[str]]:
        return {
            "market_price": list(RL_PRICE_FIELDS),
            "market_liquidity": list(RL_LIQUIDITY_FIELDS),
            "market_factor": list(RL_FACTOR_FIELDS),
            "account_state": ["cash", "shares", "position_value", "net_worth", "position_pct", "drawdown_penalty", "turnover_penalty"],
        }
