import { apiClient } from './client'

const BACKTEST_REQUEST_TIMEOUT_MS = 120000

export interface BacktestDiagnostics {
  signal_counts?: Record<string, number>
  rl_action_counts?: Record<string, number>
  no_trade_reason_counts?: Record<string, number>
  no_trade_samples?: Array<Record<string, unknown>>
  zero_trade?: boolean
}

export interface BacktestResearchReport {
  format: 'markdown'
  content: string
}

export interface BacktestRunRequest {
  symbol: string
  strategy_id?: number | null
  strategy_type?: 'moving_average' | 'macd' | 'rl_trading' | 'rsi_reversal' | 'bollinger_band' | 'kdj_momentum' | 'signal_fusion'
  start_date?: string | null
  end_date?: string | null
  source?: string
  adjustflag?: string
  initial_cash?: number
  commission_rate?: number
  slippage_rate?: number
  max_position_pct?: number
  parameters?: Record<string, unknown>
}

export interface PortfolioBacktestRequest extends Omit<BacktestRunRequest, 'symbol'> {
  symbol?: string
  symbols: string[]
  weights?: number[] | null
}

export interface BacktestOptimizationRequest extends BacktestRunRequest {
  parameter_grid: Record<string, Array<string | number | boolean | null>>
  target_metric?: 'total_return_pct' | 'max_drawdown_pct' | 'sharpe_ratio' | 'final_net_worth'
  sort_direction?: 'asc' | 'desc'
  out_of_sample?: { start_date?: string | null; end_date?: string | null } | null
}

export interface BacktestRunResponse {
  status: string
  strategy_id: number | null
  strategy_name: string | null
  strategy_type: string
  symbol: string
  source: string
  adjustflag: string
  bars: number
  initial_cash: number
  final_net_worth: number
  total_return_pct: number
  max_drawdown_pct: number
  trade_count: number
  equity_curve: Array<Record<string, unknown>>
  trades: Array<Record<string, unknown>>
  events: Array<Record<string, unknown>>
  summary: Record<string, unknown> & { diagnostics?: BacktestDiagnostics; research_report?: BacktestResearchReport }
}

export interface PortfolioBacktestResponse extends BacktestRunResponse {
  symbols: string[]
  weights: number[]
}

export interface OptimizationCandidate {
  rank: number
  parameters: Record<string, unknown>
  merged_parameters: Record<string, unknown>
  metric_value: number
  metrics: Record<string, unknown>
  bars: number
  trade_count: number
  status: string
}

export interface BacktestOptimizationResponse {
  status: string
  strategy_id: number | null
  strategy_name: string | null
  strategy_type: string
  symbol: string
  source: string
  adjustflag: string
  target_metric: string
  sort_direction: string
  bars: number
  parameter_grid: Record<string, Array<string | number | boolean | null>>
  combinations: number
  candidates: OptimizationCandidate[]
  matrix: Array<Record<string, unknown>>
  best_candidate: OptimizationCandidate | null
  out_of_sample: Record<string, unknown> | null
  summary: Record<string, unknown>
}

export interface BacktestJobResponse {
  job_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | string
  progress_step: number
  progress_total: number
  progress_pct: number
  progress_label: string
  progress_details: string[]
  created_at: string | null
  updated_at: string | null
  started_at: string | null
  finished_at: string | null
  result: BacktestRunResponse | PortfolioBacktestResponse | null
  error: string | null
  payload: Record<string, unknown>
}

export interface BacktestOptimizationJobResponse {
  job_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | string
  progress_step: number
  progress_total: number
  progress_pct: number
  progress_label: string
  progress_details: string[]
  created_at: string | null
  updated_at: string | null
  started_at: string | null
  finished_at: string | null
  result: BacktestOptimizationResponse | null
  error: string | null
  payload: Record<string, unknown>
}

export interface BacktestOptimizationHistoryItem {
  job_id: string
  created_at: string | null
  updated_at: string | null
  symbol: string
  strategy_type: string
  strategy_id: number | null
  strategy_name: string | null
  target_metric: string
  best_parameters: Record<string, unknown>
  best_result: Record<string, unknown>
  out_of_sample: Record<string, unknown> | null
  payload: Record<string, unknown>
}

export interface BacktestDailyReviewResponse {
  status: string
  review_date: string | null
  headline: string
  backtest: BacktestRunResponse
  highlights: string[]
  risks: string[]
  next_actions: string[]
}

export interface DailyReviewArchiveItem {
  id: number
  review_date: string | null
  symbol: string
  strategy_id: number | null
  strategy_name: string | null
  strategy_type: string
  headline: string
  highlights: string[]
  risks: string[]
  next_actions: string[]
  backtest_summary: Record<string, unknown>
  payload: Record<string, unknown>
  created_at: string
  updated_at: string
}

export async function runBacktest(payload: BacktestRunRequest): Promise<BacktestRunResponse> {
  const { data } = await apiClient.post('/backtest/run', payload, { timeout: BACKTEST_REQUEST_TIMEOUT_MS })
  return data
}

export async function runPortfolioBacktest(payload: PortfolioBacktestRequest): Promise<PortfolioBacktestResponse> {
  const { data } = await apiClient.post('/backtest/portfolio/run', payload, { timeout: BACKTEST_REQUEST_TIMEOUT_MS })
  return data
}

export async function buildBacktestDailyReview(payload: BacktestRunRequest): Promise<BacktestDailyReviewResponse> {
  const { data } = await apiClient.post('/backtest/daily-review', payload, { timeout: BACKTEST_REQUEST_TIMEOUT_MS })
  return data
}

export async function fetchDailyReviews(params?: { review_date?: string; symbol?: string; strategy_id?: number; limit?: number }): Promise<{ reviews: DailyReviewArchiveItem[] }> {
  const { data } = await apiClient.get('/reviews/daily', { params })
  return data
}

export async function submitBacktestJob(payload: BacktestRunRequest): Promise<BacktestJobResponse> {
  const { data } = await apiClient.post('/backtest/jobs', payload)
  return data
}

export async function fetchBacktestJob(jobId: string): Promise<BacktestJobResponse> {
  const { data } = await apiClient.get(`/backtest/jobs/${jobId}`)
  return data
}

export async function fetchLatestBacktestJob(): Promise<BacktestJobResponse | null> {
  try {
    const { data } = await apiClient.get('/backtest/jobs/latest')
    return data
  } catch (error: unknown) {
    if (typeof error === 'object' && error !== null && 'response' in error) {
      const response = (error as { response?: { status?: number } }).response
      if (response?.status === 404) {
        return null
      }
    }
    throw error
  }
}

export async function submitPortfolioBacktestJob(payload: PortfolioBacktestRequest): Promise<BacktestJobResponse> {
  const { data } = await apiClient.post('/backtest/portfolio/jobs', payload)
  return data
}

export async function fetchPortfolioBacktestJob(jobId: string): Promise<BacktestJobResponse> {
  const { data } = await apiClient.get(`/backtest/portfolio/jobs/${jobId}`)
  return data
}

export async function submitBacktestOptimizationJob(payload: BacktestOptimizationRequest): Promise<BacktestOptimizationJobResponse> {
  const { data } = await apiClient.post('/backtest/optimizations/jobs', payload)
  return data
}

export async function fetchBacktestOptimizationJob(jobId: string): Promise<BacktestOptimizationJobResponse> {
  const { data } = await apiClient.get(`/backtest/optimizations/jobs/${jobId}`)
  return data
}

export async function fetchLatestBacktestOptimizationJob(): Promise<BacktestOptimizationJobResponse | null> {
  try {
    const { data } = await apiClient.get('/backtest/optimizations/jobs/latest')
    return data
  } catch (error: unknown) {
    if (typeof error === 'object' && error !== null && 'response' in error) {
      const response = (error as { response?: { status?: number } }).response
      if (response?.status === 404) {
        return null
      }
    }
    throw error
  }
}

export async function fetchBacktestOptimizationHistory(): Promise<BacktestOptimizationHistoryItem[]> {
  const { data } = await apiClient.get('/backtest/optimizations/history')
  return data
}

export { fetchEquityCurve, fetchMonthlyStats, fetchReportingSummary, fetchYearlyStats } from './reporting'
