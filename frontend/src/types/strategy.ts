export interface StrategyItem {
  id: number
  tenant_id: string
  name: string
  strategy_type: string
  status: string
  parameters: Record<string, number | string | boolean>
  latest_signal: string
  signal_symbol: string
}
