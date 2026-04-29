import { apiClient } from './client'
import type { PositionItem as SharedPositionItem } from '../types/position'

export interface PositionItem {
  id: number
  tenant_id: string
  account_id: number
  symbol: string
  name: string | null
  market: string
  quantity: number
  available_quantity: number
  average_cost: string
  last_price: string
  unrealized_pnl: string
  realized_pnl: string
  stop_loss_price: string | null
  take_profit_price: string | null
  strategy_add_count: number
  exit_guard_status: 'inactive' | 'active' | 'triggered'
  exit_trigger_reason: 'stop_loss' | 'take_profit' | null
  exit_triggered_at: string | null
}

export async function fetchPositions(): Promise<SharedPositionItem[]> {
  const { data } = await apiClient.get('/positions')
  return data
}
