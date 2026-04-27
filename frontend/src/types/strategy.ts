export type StrategyExecutionMode = 'signal_only' | 'auto_trade'
export type StrategyStatus = 'draft' | 'active' | 'paused'
export type StrategySignalAction = 'buy' | 'sell' | 'reduce' | 'hold'
export type StrategySignalStrength = 'strong' | 'normal' | 'weak'

export interface StrategySignalPayload {
  signal: StrategySignalAction
  strength?: StrategySignalStrength | null
  trigger_reason?: string | null
  entry_price_ref?: number | null
  stop_loss_price?: number | null
  take_profit_price?: number | null
  position_pct?: number | null
  market_regime?: string | null
  requires_recommendation_confirmation?: boolean
  recommendation_confirmed?: boolean | null
  recommendation_score?: number | null
  recommendation_timing?: string | null
  execution_blockers?: string[]
  [key: string]: string | number | boolean | string[] | null | undefined
}

export interface StrategyItem {
  id: number
  tenant_id: string
  name: string
  symbol: string
  strategy_type: string
  status: StrategyStatus
  execution_mode: StrategyExecutionMode
  parameters: Record<string, number | string | boolean>
  latest_signal: StrategySignalAction
  latest_signal_summary: string | null
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
  signal: StrategySignalPayload
  execution_mode: StrategyExecutionMode | null
  order_submitted: boolean
  order_id: number | null
  order_status: string | null
  side: 'buy' | 'sell' | null
  quantity: number | null
  price: number | null
  reason: string | null
  strength: StrategySignalStrength | null
  trigger_reason: string | null
  stop_loss_price: number | null
  take_profit_price: number | null
  position_pct: number | null
  recommendation_confirmed: boolean | null
  execution_blockers: string[]
  created_at: string
}
