import { apiClient } from './client'
import type {
  SmartSelectionConfig,
  SmartSelectionConfigUpdatePayload,
  SmartSelectionHistory,
  SmartSelectionLatest,
  SmartSelectionRunDispatch,
} from '../types/smartSelection'

export async function fetchSmartSelectionConfig(): Promise<SmartSelectionConfig> {
  const { data } = await apiClient.get('/smart-selection/config')
  return data
}

export async function updateSmartSelectionConfig(
  payload: SmartSelectionConfigUpdatePayload,
): Promise<SmartSelectionConfig> {
  const { data } = await apiClient.put('/smart-selection/config', payload)
  return data
}

export async function fetchLatestSmartSelection(): Promise<SmartSelectionLatest> {
  const { data } = await apiClient.get('/smart-selection/latest')
  return data
}

export async function fetchSmartSelectionHistory(limit = 10): Promise<SmartSelectionHistory> {
  const { data } = await apiClient.get('/smart-selection/history', { params: { limit } })
  return data
}

export async function runSmartSelection(): Promise<SmartSelectionRunDispatch> {
  const { data } = await apiClient.post('/smart-selection/run')
  return data
}
