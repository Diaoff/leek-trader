from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.schemas.ai import AiAgentRunRequest, AiAgentType, AiStructuredResult


@dataclass(frozen=True)
class AiAgentSpec:
    agent_type: AiAgentType
    system_prompt: str
    task_prompt: str
    structured_output_required: bool = True


AGENT_SPECS: dict[AiAgentType, AiAgentSpec] = {
    AiAgentType.RESEARCH_AGENT: AiAgentSpec(
        agent_type=AiAgentType.RESEARCH_AGENT,
        system_prompt="你是一名股票研究助手，负责整理行情、新闻、讨论和历史 CSV 形成研究摘要。",
        task_prompt="请输出 JSON：summary、drivers、risks、watchlist、data_gaps。不要给出确定性收益承诺。",
    ),
    AiAgentType.PARAMETER_ADVISOR: AiAgentSpec(
        agent_type=AiAgentType.PARAMETER_ADVISOR,
        system_prompt="你是一名策略参数顾问，只根据当前参数、回测和优化结果给出可执行建议，不自动改写参数。",
        task_prompt="请输出 JSON：recommended_parameters、rationale、validation_plan、out_of_sample_warning、next_actions。必须提醒样本外验证。",
    ),
    AiAgentType.RISK_EXPLAINER: AiAgentSpec(
        agent_type=AiAgentType.RISK_EXPLAINER,
        system_prompt="你是一名风控解释助手，负责用清晰中文解释拒单原因、检查项和规则版本。",
        task_prompt="请输出 JSON：decision、rejection_reason、triggered_checks、rule_version、recoverable_actions。只解释拒单上下文，不分析股票走势。",
    ),
}


def build_agent_messages(
    request: AiAgentRunRequest,
    context: dict[str, Any],
) -> list[dict[str, str]]:
    spec = AGENT_SPECS[request.agent_type]
    payload = {
        "agent_type": request.agent_type.value,
        "task": spec.task_prompt,
        "structured_output_required": spec.structured_output_required,
        "symbol": request.symbol,
        "strategy_type": request.strategy_type,
        "result_ref": request.result_ref,
        "context": context,
    }
    return [
        {"role": "system", "content": spec.system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str)},
    ]


def parse_structured_content(content: str) -> AiStructuredResult:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return AiStructuredResult(parse_status="succeeded", data=parsed, raw_content=None)
    except ValueError:
        pass
    return AiStructuredResult(parse_status="failed", data=None, raw_content=content)
