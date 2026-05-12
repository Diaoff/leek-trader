export interface MonitoringOperationsMetrics {
  status: string
  generated_at: string
  window_days: number
  market_data: {
    status: string
    latest_trade_date: string | null
    staleness_days: number | null
    daily_bar_rows: number
    symbol_count: number
    source_count: number
  }
  strategy_execution: {
    window_days: number
    total_runs: number
    succeeded_runs: number
    failed_runs: number
    success_rate: number | null
    latest_run_at: string | null
  }
  trading: {
    window_days: number
    total_orders: number
    filled_orders: number
    rejected_orders: number
    cancelled_orders: number
    pending_orders: number
    trade_count: number
    order_success_rate: number | null
    latest_order_at: string | null
    latest_trade_at: string | null
  }
}

export interface MonitoringAsyncTaskSummaryItem {
  key: string
  display_name: string
  task_name: string
  schedule_name: string
  schedule_seconds: number | null
  schedule_cron: string | null
  retry_policy: {
    autoretry_for: string[]
    retry_backoff: boolean
    retry_jitter: boolean
    max_retries: number | null
  }
  stats_source: 'database' | 'process' | 'empty'
  stats: {
    task_name: string
    started: number
    succeeded: number
    failed: number
    retried: number
    last_task_id: string | null
    last_started_at: string | null
    last_succeeded_at: string | null
    last_failed_at: string | null
    last_retried_at: string | null
    last_error: string | null
    last_retry_error: string | null
  }
}

export interface MonitoringAsyncTaskSummary {
  tasks: MonitoringAsyncTaskSummaryItem[]
  note: string
  panel: {
    ready: boolean
    task_count: number
    persisted_stats_enabled: boolean
    log_dir: string
  }
}

export interface MonitoringLogPayload {
  logs: string[]
  count: number
  total: number
}

export interface MonitoringSystemStats {
  cpu_percent?: number
  memory?: {
    total: number
    available: number
    used: number
    percent: number
  }
  disk?: {
    total: number
    used: number
    free: number
    percent: number
  }
  pid?: number
  timestamp?: string
  message?: string
}
