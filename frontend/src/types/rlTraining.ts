export type RLTrainingScope = 'watchlist' | 'special_attention' | 'smart_selection' | 'manual'
export type RLModelStatus = 'draft' | 'validated' | 'active' | 'retired'

export interface RLTrainingScopeOption {
  key: RLTrainingScope
  label: string
  description: string
}

export interface RLTrainingSymbol {
  symbol: string
  name: string | null
  source: string
}

export interface RLTrainingResolveRequest {
  scope?: RLTrainingScope
  scopes?: RLTrainingScope[]
  symbols?: string[]
  limit?: number
}

export interface RLTrainingResolveResponse {
  scope: RLTrainingScope
  count: number
  symbols: RLTrainingSymbol[]
}

export interface RLTrainingRequest extends RLTrainingResolveRequest {
  model_name: string
  algorithm?: 'ppo_trading'
  start_date?: string | null
  end_date?: string | null
  source?: string
  adjustflag?: string
  exclude_suspended?: boolean
  total_timesteps?: number
  train_split_pct?: number
  ppo_n_steps?: number
  ppo_batch_size?: number
  ppo_learning_rate?: number
  initial_cash?: number
  commission_rate?: number
  slippage_rate?: number
  reward_mode?: 'net_worth_change' | 'excess_return' | 'drawdown_penalty' | 'risk_adjusted_excess_return'
  max_position_pct?: number
  ma_short_window?: number
  ma_long_window?: number
  drawdown_penalty_coef?: number
  turnover_penalty_coef?: number
  min_validation_bars?: number
}

export interface RLModelValidation {
  passed: boolean
  blockers: string[]
  warnings: string[]
}

export interface RLModelArtifact {
  model_id: string
  name: string
  status: RLModelStatus
  algorithm: string
  created_at: string
  updated_at: string
  scope: string
  symbols: RLTrainingSymbol[]
  config: Record<string, unknown>
  training: Record<string, unknown>
  splits?: Record<string, unknown>
  metrics: Record<string, unknown>
  validation: RLModelValidation | Record<string, unknown>
  evaluations: Array<Record<string, unknown>>
  dataset_manifest: Record<string, unknown>
}

export interface RLTrainingJob {
  job_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  progress_step: number
  progress_total: number
  progress_pct: number
  progress_label: string | null
  progress_details: string[]
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
  model_id: string | null
  model: RLModelArtifact | null
  error: string | null
}

export interface RLModelCompareItem {
  model_id: string
  name: string
  status: RLModelStatus
  algorithm: string
  scope: string
  symbol_count: number
  start_date: string | null
  end_date: string | null
  avg_total_return_pct: number | null
  avg_max_drawdown_pct: number | null
  avg_excess_return_pct: number | null
  trade_count: number | null
  validation_passed: boolean
  blockers: string[]
  created_at: string | null
  updated_at: string | null
}
