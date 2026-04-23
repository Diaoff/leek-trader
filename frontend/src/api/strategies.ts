import { apiClient } from './client'
import type { StrategyItem } from '../types/strategy'

export interface CreateStrategyPayload {
  name: string
  symbol: string
  strategy_type: string
  parameters: Record<string, number | string | boolean>
}

export interface UpdateStrategyPayload {
  name?: string
  symbol?: string
  status?: string
  parameters?: Record<string, number | string | boolean>
}

export interface StrategyRunResult {
  id: number
  strategy_id: number
  status: string
  signal: Record<string, string | number | boolean | null>
  created_at: string
}

export async function fetchStrategies(): Promise<StrategyItem[]> {
  const { data } = await apiClient.get('/strategies')
  return data
}

export async function createStrategy(payload: CreateStrategyPayload): Promise<StrategyItem> {
  const { data } = await apiClient.post('/strategies', payload)
  return data
}

export async function updateStrategy(strategyId: number, payload: UpdateStrategyPayload): Promise<StrategyItem> {
  const { data } = await apiClient.patch(`/strategies/${strategyId}`, payload)
  return data
}

export async function runStrategy(strategyId: number): Promise<StrategyRunResult> {
  const { data } = await apiClient.post(`/strategies/${strategyId}/run`)
  return data
}
