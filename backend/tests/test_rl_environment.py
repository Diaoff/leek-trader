from app.market.rl_environment import RLActionDecoder, RLEpisodeConfig, RLEpisodeSimulator, RewardCalculator


def _record(trade_date: str, close_price: float) -> dict[str, object]:
    return {
        "symbol": "sh600000",
        "trade_date": trade_date,
        "open_price": close_price,
        "close_price": close_price,
        "high_price": close_price,
        "low_price": close_price,
        "volume": 1000000.0,
        "turnover": close_price * 1000000.0,
        "trade_status": 1,
        "is_st": False,
    }


def test_action_decoder_accepts_tuple_and_clamps_target_pct() -> None:
    action = RLActionDecoder.decode((0.5, 1.5))

    assert action.action_type == "buy"
    assert action.target_position_pct == 1.0


def test_action_decoder_handles_malformed_actions_as_hold() -> None:
    tuple_action = RLActionDecoder.decode(["bad", "value"], encoding="rl_stock_one_based")
    dict_action = RLActionDecoder.decode({"action_type": "buy", "target_position_pct": "bad"})

    assert tuple_action.action_type == "hold"
    assert tuple_action.target_position_pct == 0.0
    assert dict_action.action_type == "buy"
    assert dict_action.target_position_pct == 0.0


def test_reward_calculator_can_use_excess_return() -> None:
    reward = RewardCalculator("excess_return").calculate(
        net_worth=110.0,
        previous_net_worth=100.0,
        benchmark_return=0.04,
        drawdown_pct=0.0,
    )

    assert round(reward, 4) == 0.06


def test_reward_calculator_risk_adjusted_excess_return_penalizes_risk() -> None:
    clean = RewardCalculator("risk_adjusted_excess_return").calculate(
        net_worth=105.0,
        previous_net_worth=100.0,
        benchmark_return=0.02,
        drawdown_pct=0.0,
        turnover_pct=0.0,
        cost_pct=0.0,
    )
    penalized = RewardCalculator("risk_adjusted_excess_return").calculate(
        net_worth=105.0,
        previous_net_worth=100.0,
        benchmark_return=0.02,
        drawdown_pct=20.0,
        turnover_pct=1.0,
        cost_pct=0.01,
    )

    assert round(clean, 4) == 0.03
    assert penalized < clean


def test_episode_simulator_buy_and_hold_generates_equity_curve() -> None:
    simulator = RLEpisodeSimulator(RLEpisodeConfig(initial_cash=1000.0, commission_rate=0.0, slippage_rate=0.0))

    result = simulator.simulate([_record("2026-04-20", 10.0), _record("2026-04-21", 12.0)], policy_name="buy_and_hold")

    assert result.status == "completed"
    assert len(result.steps) == 2
    assert result.steps[0].shares == 100
    assert result.final_net_worth == 1200.0
    assert result.total_return_pct == 20.0
    assert result.steps[1].observation["account"]["position_pct"] == 1.0


def test_episode_simulator_cash_policy_stays_flat() -> None:
    simulator = RLEpisodeSimulator(RLEpisodeConfig(initial_cash=1000.0, commission_rate=0.0, slippage_rate=0.0))

    result = simulator.simulate([_record("2026-04-20", 10.0), _record("2026-04-21", 12.0)], policy_name="cash")

    assert result.final_net_worth == 1000.0
    assert result.total_return_pct == 0.0
    assert all(step.shares == 0 for step in result.steps)


def test_episode_simulator_exposes_standard_trajectory_tables() -> None:
    simulator = RLEpisodeSimulator(RLEpisodeConfig(initial_cash=1000.0, commission_rate=0.0, slippage_rate=0.0))

    result = simulator.simulate([_record("2026-04-20", 10.0), _record("2026-04-21", 12.0)], policy_name="buy_and_hold")
    payload = result.to_dict()

    assert payload["equity_curve"][1]["net_worth"] == result.final_net_worth
    assert payload["actions"][0]["shares_delta"] == 100
    assert payload["positions"][1]["position_pct"] == 1.0
    assert payload["rewards"][1]["portfolio_return"] == 0.2
    assert payload["rewards"][1]["reward_mode"] == "net_worth_change"


def test_action_decoder_accepts_rl_stock_one_based_encoding() -> None:
    buy = RLActionDecoder.decode([1, 0.5], encoding="rl_stock_one_based")
    sell = RLActionDecoder.decode([2, 0.25], encoding="rl_stock_one_based")
    hold = RLActionDecoder.decode([3, 1.0], encoding="rl_stock_one_based")

    assert buy.action_type == "buy"
    assert buy.target_position_pct == 0.5
    assert sell.action_type == "sell"
    assert sell.target_position_pct == 0.75
    assert hold.action_type == "hold"


def test_episode_simulator_replays_action_sequence_and_reports_risk_metrics() -> None:
    simulator = RLEpisodeSimulator(RLEpisodeConfig(initial_cash=1000.0, commission_rate=0.0, slippage_rate=0.0))

    result = simulator.simulate(
        [_record("2026-04-20", 10.0), _record("2026-04-21", 12.0), _record("2026-04-22", 11.0)],
        policy_name="cash",
        action_sequence=[[1, 1.0], [3, 0.0], [2, 1.0]],
        action_encoding="rl_stock_one_based",
    )

    assert result.policy == "action_replay"
    assert [action["action_type"] for action in result.actions] == ["buy", "hold", "sell"]
    assert result.actions[0]["source"] == "replay"
    assert result.actions[-1]["shares_delta"] == -100
    assert result.summary["action_replay"] == {
        "enabled": True,
        "provided_actions": 3,
        "encoding": "rl_stock_one_based",
        "missing_action_count": 0,
    }
    assert result.summary["risk_metrics"]["turnover_pct"] == 210.0
    assert result.summary["risk_metrics"]["win_rate_pct"] == 50.0
