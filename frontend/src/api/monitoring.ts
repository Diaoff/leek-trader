import { apiClient } from './client'
import type {
  MonitoringAsyncTaskSummary,
  MonitoringLogPayload,
  MonitoringOperationsMetrics,
  MonitoringSystemStats,
} from '../types/monitoring'

export async function fetchOperationsMetrics(windowDays = 7): Promise<MonitoringOperationsMetrics> {
  const { data } = await apiClient.get('/monitoring/operations/metrics', { params: { window_days: windowDays } })
  return data
}

export async function fetchAsyncTaskSummary(): Promise<MonitoringAsyncTaskSummary> {
  const { data } = await apiClient.get('/monitoring/async-tasks/summary')
  return data
}

export async function fetchMonitoringLogs(limit = 20): Promise<MonitoringLogPayload> {
  const { data } = await apiClient.get('/monitoring/logs/latest', { params: { limit } })
  return data
}

export async function fetchSystemStats(): Promise<MonitoringSystemStats> {
  const { data } = await apiClient.get('/monitoring/system/stats')
  return data
}
