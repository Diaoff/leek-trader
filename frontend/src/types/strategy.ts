export interface StrategyItem {
  id: number
  tenant_id: string
  name: string
  symbol: string
  strategy_type: string
  status: string
  parameters: Record<string, number | string | boolean>
  latest_signal: string
  signal_symbol: string
  latest_run_status: string | null
  latest_run_at: string | null
  run_count_today: number
  total_run_count: number
}
