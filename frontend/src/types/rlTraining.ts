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
  scope: RLTrainingScope
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
  start_date?: string | null
  end_date?: string | null
  source?: string
  adjustflag?: string
  exclude_suspended?: boolean
  episodes?: number
  learning_rate?: number
  discount_factor?: number
  exploration_rate?: number
  initial_cash?: number
  commission_rate?: number
  slippage_rate?: number
  reward_mode?: 'net_worth_change' | 'excess_return' | 'drawdown_penalty'
  max_position_pct?: number
  ma_short_window?: number
  ma_long_window?: number
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
  scope: RLTrainingScope
  symbols: RLTrainingSymbol[]
  config: Record<string, unknown>
  training: Record<string, unknown>
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
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
  model_id: string | null
  model: RLModelArtifact | null
  error: string | null
}
