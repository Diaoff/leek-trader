import { apiClient } from './client'

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

export const fetchStrategies = async (): Promise<StrategyItem[]> => {
  const { data } = await apiClient.get('/strategies')
  return data
}
