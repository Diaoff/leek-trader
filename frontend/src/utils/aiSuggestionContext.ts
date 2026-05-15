export type AiParameterSource = 'template' | 'example' | 'empty'

export type AiSuggestionSource = 'strategy-template' | 'backtest-result' | 'optimization-result'

export interface AiSuggestionQueryInput {
  symbol: string
  strategyType: string
  optimizationJobId?: string | null
  backtestJobId?: string | null
  strategyRunId?: string | number | null
  orderId?: string | number | null
  correlationId?: string | null
  currentParameters?: string | null
  templateKey?: string | null
  templateName?: string | null
  templateParameters?: string | null
  parameterSource?: AiParameterSource | null
  source?: AiSuggestionSource | null
}

export function firstQueryString(value: unknown): string {
  if (Array.isArray(value)) {
    return typeof value[0] === 'string' ? value[0] : ''
  }
  return typeof value === 'string' ? value : ''
}

export function parseJsonObject(raw: string | null | undefined): Record<string, unknown> {
  if (!raw) {
    return {}
  }
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

export function buildAiSuggestionQuery(input: AiSuggestionQueryInput): Record<string, string> {
  const query: Record<string, string> = {
    symbol: input.symbol.trim(),
    strategyType: input.strategyType.trim(),
  }

  const optionalEntries: Array<[string, string | null | undefined]> = [
    ['optimizationJobId', input.optimizationJobId],
    ['backtestJobId', input.backtestJobId],
    ['strategyRunId', input.strategyRunId != null ? String(input.strategyRunId) : null],
    ['orderId', input.orderId != null ? String(input.orderId) : null],
    ['correlationId', input.correlationId],
    ['currentParameters', input.currentParameters],
    ['templateKey', input.templateKey],
    ['templateName', input.templateName],
    ['templateParameters', input.templateParameters],
    ['parameterSource', input.parameterSource],
    ['source', input.source],
  ]

  optionalEntries.forEach(([key, value]) => {
    const normalized = typeof value === 'string' ? value.trim() : value
    if (typeof normalized === 'string' && normalized) {
      query[key] = normalized
    }
  })

  return query
}

export function describeAiSuggestionSource(source: AiSuggestionSource | null | undefined): string {
  const mapping: Record<AiSuggestionSource, string> = {
    'strategy-template': '模板研究',
    'backtest-result': '回测结果',
    'optimization-result': '参数扫描',
  }
  return source ? (mapping[source] ?? source) : '手动输入'
}

export function describeAiParameterSource(source: AiParameterSource | null | undefined): string {
  const mapping: Record<AiParameterSource, string> = {
    template: '模板参数',
    example: '示例参数',
    empty: '空参数',
  }
  return source ? (mapping[source] ?? source) : '--'
}

export function summarizeObject(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) {
    return '--'
  }
  return Object.entries(value).map(([key, item]) => `${key}:${String(item)}`).join(' · ')
}
