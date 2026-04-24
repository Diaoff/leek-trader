export type StrategyExecutionMode = 'signal_only' | 'auto_trade'
export type StrategyStatus = 'draft' | 'active' | 'paused'

export interface StrategyItem {
  id: number
  tenant_id: string
  name: string
  symbol: string
  strategy_type: string
  status: StrategyStatus
  execution_mode: StrategyExecutionMode
  parameters: Record<string, number | string | boolean>
  latest_signal: string
  signal_symbol: string
  latest_run_status: string | null
  latest_run_at: string | null
  run_count_today: number
  total_run_count: number
}

export interface StrategyRunResult {
  id: number
  strategy_id: number
  status: string
  signal: Record<string, string | number | boolean | null>
  execution_mode: StrategyExecutionMode | null
  order_submitted: boolean
  order_id: number | null
  order_status: string | null
  side: 'buy' | 'sell' | null
  quantity: number | null
  price: number | null
  reason: string | null
  created_at: string
}
