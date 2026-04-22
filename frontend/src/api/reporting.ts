import { apiClient } from './client'

export interface ReportingSummary {
  trade_count: number
  realized_pnl: number
  win_rate: number
  cumulative_return: number
  profit_factor: number
  max_drawdown: number
  avg_win: number
  avg_loss: number
}

export interface EquityCurvePoint {
  label: string
  total_equity: number
}

export interface PeriodStat {
  period: string
  trade_count: number
  realized_pnl: number
  ending_equity: number
}

export async function fetchReportingSummary(): Promise<ReportingSummary> {
  const { data } = await apiClient.get('/reporting/summary')
  return data
}

export async function fetchEquityCurve(): Promise<EquityCurvePoint[]> {
  const { data } = await apiClient.get('/reporting/equity-curve')
  return data
}

export async function fetchMonthlyStats(): Promise<PeriodStat[]> {
  const { data } = await apiClient.get('/reporting/monthly-stats')
  return data
}

export async function fetchYearlyStats(): Promise<PeriodStat[]> {
  const { data } = await apiClient.get('/reporting/yearly-stats')
  return data
}
