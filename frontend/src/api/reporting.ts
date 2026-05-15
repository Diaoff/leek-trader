import { apiClient } from './client'
import type { ReportingEvent } from '../types/reporting'

export interface ReportingSummary {
  trade_count: number
  realized_pnl: number
  win_rate: number
  cumulative_return: number
  profit_factor: number
  max_drawdown: number
  avg_win: number
  avg_loss: number
  annualized_return_pct: number | null
  annualized_volatility_pct: number | null
  sharpe_ratio: number | null
  calmar_ratio: number | null
}

export interface TotalAssetCurvePoint {
  label: string
  total_equity: number
}

export type EquityCurvePoint = TotalAssetCurvePoint

export interface PeriodStat {
  period: string
  trade_count: number
  realized_pnl: number
  ending_equity: number
}

export interface ReportingEventQueryParams {
  start_at?: string
  end_at?: string
  strategy_id?: number
  strategy_run_id?: number
  order_id?: number
  symbol?: string
  event_type?: string
  correlation_id?: string
}

export async function fetchReportingSummary(): Promise<ReportingSummary> {
  const { data } = await apiClient.get('/reporting/summary')
  return data
}

export async function fetchTotalAssetCurve(): Promise<TotalAssetCurvePoint[]> {
  const { data } = await apiClient.get('/reporting/equity-curve')
  return data
}

export const fetchEquityCurve = fetchTotalAssetCurve

export async function fetchMonthlyStats(): Promise<PeriodStat[]> {
  const { data } = await apiClient.get('/reporting/monthly-stats')
  return data
}

export async function fetchYearlyStats(): Promise<PeriodStat[]> {
  const { data } = await apiClient.get('/reporting/yearly-stats')
  return data
}

export async function fetchReportingEvents(params?: ReportingEventQueryParams): Promise<ReportingEvent[]> {
  const { data } = await apiClient.get('/reporting/events', { params })
  return data
}

export function tradesCsvExportUrl(): string {
  return '/api/v1/reporting/export/trades.csv'
}

export async function downloadTradesCsv(): Promise<void> {
  const response = await apiClient.get('/reporting/export/trades.csv', { responseType: 'blob' })
  const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'trades.csv'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
