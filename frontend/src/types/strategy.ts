export type StrategyExecutionMode = 'signal_only' | 'auto_trade'
export type StrategyStatus = 'draft' | 'active' | 'paused'
export type StrategySignalAction = 'buy' | 'sell' | 'reduce' | 'hold'
export type StrategySignalStrength = 'strong' | 'normal' | 'weak'
export type StrategyTargetType = 'single_symbol' | 'special_attention'

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
  confirmation_source?: 'smart_selection' | 'special_attention_watchlist' | 'simulation_bypass' | 'none' | null
  recommendation_snapshot_date?: string | null
  position_add_path?: 'new_position' | 'first_add' | 'blocked_repeat_add' | null
  recommendation_score?: number | null
  recommendation_timing?: string | null
  execution_blockers?: string[]
  intraday_timing_status?: 'confirmed' | 'blocked' | 'unavailable' | 'disabled' | null
  intraday_trigger_reason?: string | null
  intraday_vwap?: number | null
  intraday_volume_ratio?: number | null
  intraday_latest_close?: number | null
  filter_passed?: boolean
  filter_reasons?: string[]
  trend_ok?: boolean | null
  volume_ok?: boolean | null
  volatility_ok?: boolean | null
  stretch_ok?: boolean | null
  market_regime_bias?: string | null
  strategy_metadata?: Record<string, unknown>
  strategy_context?: Record<string, unknown>
  standard_signal?: Record<string, unknown>
  [key: string]: string | number | boolean | string[] | Record<string, unknown> | null | undefined
}

export interface StrategyItem {
  id: number
  tenant_id: string
  name: string
  symbol: string
  target_type: StrategyTargetType
  target_config: Record<string, string | number | boolean>
  strategy_type: string
  status: StrategyStatus
  execution_mode: StrategyExecutionMode
  parameters: Record<string, number | string | boolean>
  latest_signal: StrategySignalAction
  latest_signal_summary: string | null
  readiness_status: 'draft' | 'observing' | 'paper_verified' | 'paused'
  readiness_summary: string | null
  signal_symbol: string
  signal_symbol_display: string | null
  resolved_target_count: number
  latest_run_status: string | null
  latest_run_at: string | null
  run_count_today: number
  total_run_count: number
  strategy_metadata: Record<string, unknown>
}

export interface StrategyVersionItem {
  id: number
  strategy_id: number
  version: number
  name: string
  symbol: string
  strategy_type: string
  execution_mode: StrategyExecutionMode
  target_type: StrategyTargetType
  target_config: Record<string, string | number | boolean>
  parameters: Record<string, unknown>
  created_at: string
}

export interface StrategyTemplateItem {
  key: string
  name: string
  category: string
  description: string
  scenario: string
  fit_for: string[]
  not_fit_for: string[]
  risk_note: string
  minimum_history: number
  auto_trade_allowed: boolean
  research_only: boolean
  parameter_bounds: Record<string, Record<string, unknown>>
  payload: {
    name: string
    symbol?: string | null
    target_type?: StrategyTargetType | null
    target_config?: Record<string, unknown> | null
    strategy_type: string
    execution_mode: StrategyExecutionMode
    parameters: Record<string, unknown>
  }
}

export interface StrategyCompareResult {
  items: Array<{
    key: string
    strategy_id: number
    version_id: number | null
    version: number | null
    name: string
    symbol: string
    strategy_type: string
    execution_mode: StrategyExecutionMode
    target_type: StrategyTargetType
    target_config: Record<string, unknown>
    parameters: Record<string, unknown>
    latest_run: Record<string, unknown> | null
    backtest_summary: Record<string, unknown>
    created_at: string | null
  }>
  parameter_diffs: Array<{ key: string; values: Record<string, unknown> }>
}

export interface StrategyRunItemResult {
  id: number
  symbol: string
  name: string | null
  signal: StrategySignalPayload
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
  confirmation_source: 'smart_selection' | 'special_attention_watchlist' | 'simulation_bypass' | 'none' | null
  recommendation_snapshot_date: string | null
  position_add_path: 'new_position' | 'first_add' | 'blocked_repeat_add' | null
  execution_blockers: string[]
  execution_environment: 'paper'
  created_at: string
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
  confirmation_source: 'smart_selection' | 'special_attention_watchlist' | 'simulation_bypass' | 'none' | null
  recommendation_snapshot_date: string | null
  position_add_path: 'new_position' | 'first_add' | 'blocked_repeat_add' | null
  execution_blockers: string[]
  execution_environment: 'paper'
  items: StrategyRunItemResult[]
  created_at: string
}

export interface StrategyRunHistory {
  runs: StrategyRunResult[]
}
