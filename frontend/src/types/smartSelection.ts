export interface SmartSelectionConfig {
  id: number
  tenant_id: string
  enabled: boolean
  schedule_time: string
  config_payload: Record<string, unknown>
  updated_at: string
}

export interface SmartSelectionItem {
  symbol: string
  code: string
  name: string
  score: number
  price: number | null
  change_pct: number | null
  target_price: number | null
  stop_loss_price: number | null
  tags: string[]
  reason: string
  dimension_scores: Record<string, number>
  raw_detail: Record<string, unknown>
}

export interface SmartSelectionRun {
  id: number
  task_id: string | null
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  triggered_by: string
  candidate_pool_size: number
  recommendation_count: number
  summary: string | null
  report_body: string | null
  error_message: string | null
  progress_step: number
  progress_total: number
  progress_label: string | null
  generated_at: string | null
  started_at: string
  finished_at: string | null
}

export interface SmartSelectionLatest {
  snapshot: SmartSelectionRun | null
  items: SmartSelectionItem[]
  latest_task: SmartSelectionRun | null
}

export interface SmartSelectionHistory {
  runs: SmartSelectionRun[]
}

export interface SmartSelectionRunDispatch {
  status: 'queued'
  run_id: number
  task_id: string
}

export interface SmartSelectionConfigUpdatePayload {
  enabled?: boolean
  config_payload?: Record<string, unknown>
}
