import { apiClient } from './client'
import type {
  StrategyExecutionMode,
  StrategyCompareResult,
  StrategyItem,
  StrategyRunHistory,
  StrategyRunResult,
  StrategyTargetType,
  StrategyTemplateItem,
  StrategyVersionItem,
} from '../types/strategy'

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

export async function fetchLatestStrategyRun(strategyId?: number): Promise<StrategyRunResult | null> {
  const { data } = await apiClient.get('/strategies/runs/latest', {
    params: strategyId ? { strategy_id: strategyId } : undefined,
  })
  return data
}

export async function fetchStrategyRunHistory(limit = 10, strategyId?: number): Promise<StrategyRunHistory> {
  const params: Record<string, number> = { limit }
  if (strategyId) {
    params.strategy_id = strategyId
  }
  const { data } = await apiClient.get('/strategies/runs/history', { params })
  return data
}

export async function fetchStrategyTemplates(): Promise<StrategyTemplateItem[]> {
  const { data } = await apiClient.get('/strategies/templates')
  return data
}

export async function fetchStrategyVersions(strategyId: number): Promise<StrategyVersionItem[]> {
  const { data } = await apiClient.get(`/strategies/${strategyId}/versions`)
  return data
}

export async function compareStrategies(items: Array<{ strategy_id: number; version_id?: number | null }>): Promise<StrategyCompareResult> {
  const { data } = await apiClient.post('/strategies/compare', { items })
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

export async function deleteStrategy(strategyId: number): Promise<{ status: string; id: number }> {
  const { data } = await apiClient.delete(`/strategies/${strategyId}`)
  return data
}

export async function runStrategy(strategyId: number): Promise<StrategyRunResult> {
  const { data } = await apiClient.post(`/strategies/${strategyId}/run`)
  return data
}
