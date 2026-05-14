from __future__ import annotations

from typing import Any


def build_backtest_research_report(backtest: dict[str, Any]) -> dict[str, str]:
    summary = backtest.get("summary") if isinstance(backtest.get("summary"), dict) else {}
    report = summary.get("report") if isinstance(summary.get("report"), dict) else {}
    execution_model = summary.get("execution_model") if isinstance(summary.get("execution_model"), dict) else {}
    diagnostics = summary.get("diagnostics") if isinstance(summary.get("diagnostics"), dict) else {}
    lines = [
        f"# {backtest.get('symbol', '')} 回测研究报告",
        "",
        "## 基本信息",
        f"- 策略：{backtest.get('strategy_name') or summary.get('strategy_name') or backtest.get('strategy_type')}",
        f"- 区间：{summary.get('first_trade_date')} ~ {summary.get('last_trade_date')}",
        f"- 数据源：{backtest.get('source')} / 复权：{backtest.get('adjustflag')}",
        f"- 样本数：{backtest.get('bars')}",
        "",
        "## 绩效摘要",
        f"- 初始资金：{_fmt(backtest.get('initial_cash'))}",
        f"- 期末净值：{_fmt(backtest.get('final_net_worth'))}",
        f"- 总收益率：{_fmt(backtest.get('total_return_pct'))}%",
        f"- 最大回撤：{_fmt(backtest.get('max_drawdown_pct'))}%",
        f"- 交易次数：{backtest.get('trade_count')}",
        f"- 夏普比率：{_fmt(report.get('sharpe_ratio'))}",
        f"- Calmar：{_fmt(report.get('calmar_ratio'))}",
        f"- 胜率：{_fmt(report.get('win_rate_pct'))}%",
        "",
        "## 成本与成交假设",
        f"- 手续费合计：{_fmt(summary.get('total_fees'))}",
        f"- 滑点成本估算：{_fmt(summary.get('total_slippage_cost'))}",
        f"- 未成交股数：{summary.get('total_unfilled_shares', 0)}",
        f"- 整手单位：{execution_model.get('lot_size', 100)} 股",
        f"- 最大成交量参与率：{execution_model.get('max_volume_participation')}",
        f"- 比例滑点：{execution_model.get('slippage_rate', 0)}",
        f"- 固定滑点：{execution_model.get('fixed_slippage_amount', 0)}",
        f"- 冲击滑点因子：{execution_model.get('impact_slippage_factor', 0)}",
        f"- 涨跌停处理：{execution_model.get('limit_move_policy', {})}",
        "",
        "## 信号诊断",
        f"- 信号分布：`{diagnostics.get('signal_counts', {})}`",
        f"- 标准化未交易原因：`{diagnostics.get('no_trade_reason_counts', {})}`",
        "",
        "## 风险提示",
        "- 本报告仅用于本地研究和模拟验证，不构成投资建议。",
        "- 回测结果受数据源、复权口径、成交假设、滑点和样本区间影响。",
        "- 若数据质量不足、样本过短或成交受限，应降低结论置信度。",
    ]
    markdown = "\n".join(lines).strip() + "\n"
    return {"format": "markdown", "content": markdown}


def _fmt(value: object) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)
