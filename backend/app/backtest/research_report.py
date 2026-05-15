from __future__ import annotations

from typing import Any

BACKTEST_RESEARCH_REPORT_VERSION = "phase5-markdown-v1"
DEFAULT_LIMITATIONS = (
    "它不能证明策略在未来仍然有效，也不能替代样本外验证和滚动复盘。",
    "它不能覆盖停牌、涨跌停、流动性骤降、滑点扩张和交易时段变化等所有真实成交摩擦。",
    "它不能证明参数稳定或不存在过拟合，尤其不能把单次优异结果视为可复制收益。",
    "它不是投资建议，也不能替代账户风险承受能力、仓位纪律和人工复核。",
)


def build_backtest_research_report(backtest: dict[str, Any]) -> dict[str, str]:
    summary = _mapping(backtest.get("summary"))
    report = _mapping(summary.get("report"))
    execution_model = _mapping(summary.get("execution_model"))
    diagnostics = _mapping(summary.get("diagnostics"))
    research_summary = _mapping(summary.get("research_summary"))
    sample = _mapping(research_summary.get("sample"))
    data_source = _mapping(research_summary.get("data_source"))
    quality = _mapping(research_summary.get("quality"))
    cost_model = _mapping(research_summary.get("cost_model"))
    execution_constraints = _mapping(research_summary.get("execution_constraints"))
    warnings = _string_list(research_summary.get("warnings"))
    limitations = _string_list(research_summary.get("limitations")) or list(DEFAULT_LIMITATIONS)
    parameters = _mapping(summary.get("parameters"))

    source = str(backtest.get("source") or data_source.get("requested_source") or "N/A")
    adjustflag = str(backtest.get("adjustflag") or data_source.get("adjustflag") or "N/A")
    health_summary = _join_parts([
        _health_label(data_source.get("source_health_level")),
        f"运行态 { _health_label(data_source.get('runtime_health_level')) }" if data_source.get("runtime_health_level") else None,
    ])
    sync_summary = _sync_summary(data_source)
    quality_summary = _join_parts([
        f"行数 {quality.get('rows')}" if quality.get("rows") is not None else None,
        f"停牌/异常 {quality.get('suspended_rows')}" if quality.get("suspended_rows") else None,
        f"ST {quality.get('st_rows')}" if quality.get("st_rows") else None,
        f"缺失字段 {', '.join(_string_list(quality.get('null_fields'))[:4])}" if quality.get("null_fields") else None,
    ]) or "未提供额外质量摘要"
    signal_counts = _dict_summary(diagnostics.get("signal_counts"))
    no_trade_counts = _dict_summary(diagnostics.get("no_trade_reason_counts"))
    lines = [
        f"# {backtest.get('symbol', '')} 回测研究报告",
        "",
        "## 醒目提示",
    ]
    if warnings:
        lines.extend([f"> 警示：{warning}" for warning in warnings])
    else:
        lines.append("> 警示：当前未触发额外红旗，但这并不意味着回测结论可直接外推。")
    lines.extend([
        "",
        "## 基本信息",
        f"- 策略：{backtest.get('strategy_name') or summary.get('strategy_name') or backtest.get('strategy_type')}",
        f"- 样本区间：{sample.get('start_date') or summary.get('first_trade_date') or 'N/A'} ~ {sample.get('end_date') or summary.get('last_trade_date') or 'N/A'}",
        f"- 样本数：{sample.get('bars') if sample.get('bars') is not None else backtest.get('bars')}",
        f"- 数据源：{source} / 复权：{adjustflag}",
        f"- 引擎版本：{execution_constraints.get('engine_version') or BACKTEST_RESEARCH_REPORT_VERSION}",
        "",
        "## 策略参数",
    ])
    if parameters:
        lines.extend([f"- `{key}` = {_fmt(value)}" for key, value in sorted(parameters.items())])
    else:
        lines.append("- 未提供显式策略参数")
    lines.extend([
        "",
        "## 数据与样本说明",
        f"- 数据源健康度：{health_summary or '未知'}",
        f"- 同步/降级情况：{sync_summary}",
        f"- 数据质量摘要：{quality_summary}",
    ])
    source_notes = _string_list(data_source.get("notes"))
    if source_notes:
        lines.extend([f"- 数据源备注：{note}" for note in source_notes[:3]])
    quality_notes = _string_list(quality.get("notes"))
    if quality_notes:
        lines.extend([f"- 质量备注：{note}" for note in quality_notes[:3]])
    lines.extend([
        "",
        "## 交易约束与成本假设",
        f"- 初始资金：{_fmt(backtest.get('initial_cash'))}",
        f"- 手续费率：{_fmt(cost_model.get('commission_rate'))}",
        f"- 最低佣金：{_fmt(cost_model.get('min_commission'))}",
        f"- 印花税率：{_fmt(cost_model.get('stamp_tax_rate'))}",
        f"- 比例滑点：{_fmt(cost_model.get('slippage_rate'))}",
        f"- 固定滑点：{_fmt(cost_model.get('fixed_slippage_amount'))}",
        f"- 冲击滑点因子：{_fmt(cost_model.get('impact_slippage_factor'))}",
        f"- 手续费合计：{_fmt(cost_model.get('total_fees', summary.get('total_fees')))}",
        f"- 滑点成本估算：{_fmt(cost_model.get('total_slippage_cost', summary.get('total_slippage_cost')))}",
        f"- 整手单位：{execution_constraints.get('lot_size', execution_model.get('lot_size', 100))} 股",
        f"- 最大成交量参与率：{_fmt(execution_constraints.get('max_volume_participation', execution_model.get('max_volume_participation')))}",
        f"- 最大总仓位：{_fmt(execution_constraints.get('max_position_pct'))}",
        f"- 涨跌停处理：{_limit_policy_label(execution_constraints.get('limit_move_policy', execution_model.get('limit_move_policy')))}",
        f"- 累计未成交股数：{execution_constraints.get('total_unfilled_shares', summary.get('total_unfilled_shares', 0))}",
        "",
        "## 核心绩效指标",
        f"- 期末净值：{_fmt(backtest.get('final_net_worth'))}",
        f"- 总收益率：{_fmt(backtest.get('total_return_pct'))}%",
        f"- 最大回撤：{_fmt(backtest.get('max_drawdown_pct'))}%",
        f"- 交易次数：{backtest.get('trade_count')}",
        f"- 夏普比率：{_fmt(report.get('sharpe_ratio'))}",
        f"- Calmar：{_fmt(report.get('calmar_ratio'))}",
        f"- 胜率：{_fmt(report.get('win_rate_pct'))}%",
        "",
        "## 风险提示",
        "- 本报告仅用于本地研究和模拟验证，不构成投资建议。",
        "- 回测结果受数据源、复权口径、成交假设、滑点和样本区间影响。",
        f"- 信号分布：{signal_counts}",
        f"- 未交易原因：{no_trade_counts}",
    ])
    if diagnostics.get("zero_trade"):
        lines.append("- 本次样本出现零成交，收益曲线和风险指标的解释力明显受限。")
    lines.extend([
        "",
        "## 该回测不能说明什么",
        *[f"- {item}" for item in limitations],
    ])
    markdown = "\n".join(lines).strip() + "\n"
    return {"format": "markdown", "content": markdown}


def _fmt(value: object) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _join_parts(parts: list[str | None]) -> str:
    return " / ".join(part for part in parts if part)


def _health_label(value: object) -> str:
    mapping = {
        "healthy": "健康",
        "degraded": "降级",
        "down": "不可用",
        "unknown": "未知",
        "empty": "无数据",
        "partial": "部分可用",
    }
    return mapping.get(str(value or ""), str(value or "未知"))


def _sync_summary(data_source: dict[str, Any]) -> str:
    status = str(data_source.get("history_sync_status") or "")
    fallback_source = data_source.get("fallback_source")
    if status == "fallback_success" and fallback_source:
        return f"主源未直接返回样本，已通过 {fallback_source} 回填"
    if status == "failed":
        return f"同步失败：{data_source.get('history_sync_error') or '未知错误'}"
    if status:
        return status
    if data_source.get("empty_result"):
        return "无可用历史样本"
    return "未发生额外同步或降级"


def _limit_policy_label(value: object) -> str:
    mapping = _mapping(value)
    if not mapping:
        return "未提供"
    buy = mapping.get("buy", "N/A")
    sell = mapping.get("sell", "N/A")
    return f"买入 {buy} / 卖出 {sell}"


def _dict_summary(value: object) -> str:
    payload = _mapping(value)
    if not payload:
        return "无"
    return " / ".join(f"{key} {payload[key]}" for key in sorted(payload))
