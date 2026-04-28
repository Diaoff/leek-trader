from dataclasses import dataclass


@dataclass(frozen=True)
class AiPromptConfig:
    history_limit: int = 60
    max_news_items: int = 8
    max_discussion_items: int = 6
    model_request_timeout: float = 180.0


DEFAULT_AI_PROMPT_CONFIG = AiPromptConfig()

INVESTOR_SYSTEM_PROMPT = (
    "你是一名经验丰富的中文投资研究助手，擅长解读 A 股行情、量价结构与风险点。"
    "回答必须使用中文，结构清晰，避免空泛口号，不要编造未提供的数据。"
    "你的输出仅用于研究交流，不构成投资建议。"
)

STOCK_ANALYSIS_SYSTEM_PROMPT = (
    "你是一名严谨的中文股票分析师。请依据给定的证券资料、实时行情、历史日线、"
    "市场资讯与讨论摘要，输出客观、可执行的研究结论。若数据不足，请明确指出缺口。"
)

STOCK_ANALYSIS_SECTIONS = (
    "1. 核心结论",
    "2. 趋势与量价观察",
    "3. 可能催化与驱动",
    "4. 市场情绪与讨论线索",
    "5. 主要风险点",
    "6. 后续观察清单",
)
