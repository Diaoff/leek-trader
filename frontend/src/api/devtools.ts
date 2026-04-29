import { apiClient } from './client'

export interface TradingStateResetPayload {
  confirmation: string
  initial_cash?: number | null
}

export interface TradingStateResetResult {
  account_id: number
  tenant_id: string
  account_name: string
  initial_cash: string
  available_cash: string
  total_equity: string
  deleted_counts: Record<string, number>
}

export async function resetTradingState(payload: TradingStateResetPayload): Promise<TradingStateResetResult> {
  const { data } = await apiClient.post('/devtools/reset-trading-state', payload)
  return data
}
