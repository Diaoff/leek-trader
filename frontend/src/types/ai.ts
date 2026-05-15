export type AiProvider = 'openai_compatible' | 'deepseek' | 'siliconflow' | 'ollama' | 'custom'

export interface AiConfig {
  provider: AiProvider
  base_url: string
  api_key: string
  model: string
  configured: boolean
  provider_display_name?: string | null
  provider_base_url_hint?: string | null
  provider_api_key_required?: boolean
  provider_model_hint?: string | null
}

export interface AiConfigPayload {
  provider: AiProvider
  base_url: string
  api_key: string
  model: string
}

export interface AiChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface AiChatResponse {
  content: string
  model: string
}

export interface AiSecurity {
  symbol: string
  code: string
  name: string
  market: string
  tags: string[]
}

export interface AiStockAnalysis {
  symbol: string
  security: AiSecurity
  content: string
  generated_at: string
  latest_price: number | null
  change_percent: number | null
}

export type AiAgentType = 'research_agent' | 'parameter_advisor' | 'risk_explainer'

export interface AiStructuredResult {
  parse_status: 'succeeded' | 'failed'
  data?: Record<string, unknown> | null
  raw_content?: string | null
}

export interface AiAgentRunRequest {
  agent_type: AiAgentType
  context: Record<string, unknown>
  symbol?: string | null
  strategy_type?: string | null
  result_ref?: string | null
}

export interface AiAgentRunResponse {
  agent_type: AiAgentType
  provider: AiProvider
  model: string
  content: string
  structured: AiStructuredResult
  warnings: string[]
  recoverable: boolean
}

export interface AiParameterAdviceRequest {
  symbol: string
  strategy_type: string
  current_parameters: Record<string, unknown>
  optimization_job_id?: string | null
  backtest_job_id?: string | null
  strategy_run_id?: number | null
  order_id?: number | null
  correlation_id?: string | null
}

export interface AiParameterAdviceResponse {
  symbol: string
  strategy_type: string
  provider: AiProvider
  model: string
  content: string
  structured: AiStructuredResult
  warnings: string[]
  recoverable: boolean
}

export interface AiProviderError {
  code: string
  message: string
  recoverable: boolean
  provider?: AiProvider | null
}
