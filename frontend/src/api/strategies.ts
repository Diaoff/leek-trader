import { apiClient } from './client'
import type { StrategyExecutionMode, StrategyItem, StrategyRunResult, StrategyTargetType } from '../types/strategy'

export interface CreateStrategyPayload {
  name: string
  symbol?: string
  target_type?: StrategyTargetType
  target_config?: Record<string, number | string | boolean>
  strategy_type: string
  execution_mode: StrategyExecutionMode
  parameters: Record<string, number | string | boolean>
}

export interface UpdateStrategyPayload {
  name?: string
  symbol?: string
  target_type?: StrategyTargetType
  target_config?: Record<string, number | string | boolean>
  strategy_type?: string
  status?: string
  execution_mode?: StrategyExecutionMode
  parameters?: Record<string, number | string | boolean>
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
