from typing import Any

from .config import STOCK_ANALYSIS_SECTIONS
from .data_loader import AiStockContext


def build_stock_analysis_prompt(
    security: dict[str, Any],
    context: AiStockContext,
    note: str | None,
) -> str:
    quote_lines = [
        f"证券名称：{security['name']}",
        f"证券代码：{security['code']} ({security['symbol']})",
        f"所属市场：{security['market']}",
        f"标签：{', '.join(str(tag) for tag in security.get('tags', [])) or '无'}",
    ]

    if context.quote is not None:
        quote_lines.extend(
            [
                f"最新价格：{context.quote.price}",
                f"当日涨跌幅：{context.quote.change_percent}%",
                f"成交额/成交量字段：{context.quote.volume}（字段含义取决于行情源）",
                f"总市值：{context.quote.market_cap if context.quote.market_cap is not None else '暂无'}",
                f"年初至今涨跌幅：{context.quote.ytd_change_percent if context.quote.ytd_change_percent is not None else '暂无'}",
            ]
        )
    else:
        quote_lines.append("实时行情：暂无")

    if note:
        quote_lines.append(f"用户备注：{note.strip()}")

    return (
        "请基于以下资料给出一份中文 AI 股票研究报告。\n"
        "输出结构必须包含：\n"
        f"{chr(10).join(STOCK_ANALYSIS_SECTIONS)}\n"
        "要求：\n"
        "- 明确指出结论依据来自行情、日线、资讯、讨论或用户备注中的哪类数据\n"
        "- 不要虚构新闻、公告、财务数据或不存在的模型指标\n"
        "- 若某类数据为空，请直接说明数据缺口\n"
        "- 结尾必须注明：仅供研究交流，不构成投资建议\n\n"
        f"基础资料：\n{chr(10).join(quote_lines)}\n\n"
        f"近 60 个交易日日线 CSV（来源：{context.history_source}）：\n{context.history_csv or '暂无可用历史日线数据。'}\n\n"
        f"市场资讯摘要：\n{format_context_list(context.news_items)}\n\n"
        f"讨论/情绪摘要：\n{format_context_list(context.discussion_items)}"
    )


def format_context_list(items: list[str]) -> str:
    if not items:
        return "暂无可用数据。"
    return "\n".join(f"- {item}" for item in items)
