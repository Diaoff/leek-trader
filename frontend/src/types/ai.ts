export interface AiConfig {
  base_url: string
  api_key: string
  model: string
  configured: boolean
}

export interface AiConfigPayload {
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
