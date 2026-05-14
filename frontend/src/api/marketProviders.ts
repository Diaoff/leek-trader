import { apiClient } from './client'

export interface ProviderCapability {
  name: 'quote' | 'daily_bar' | 'intraday_bar' | 'fundamental' | 'concept' | 'fund_flow' | 'index' | 'fund' | 'bond'
  supported: boolean
  fields: string[]
  notes: string[]
}

export interface ProviderProfile {
  name: string
  label: string
  capabilities: ProviderCapability[]
  requires_login: boolean
  supports_adjustment: boolean
  stable_for_backtest: boolean
  rate_limit_note: string | null
  failure_modes: string[]
}

export interface ProviderCapabilityMatrix {
  status: 'ready'
  providers: ProviderProfile[]
}

export interface MarketSourceHealthItem {
  source: string
  label: string
  status: 'healthy' | 'partial' | 'empty'
  role: 'primary' | 'fallback' | 'unavailable'
  symbol_count: number
  row_count: number
  first_trade_date: string | null
  last_trade_date: string | null
  missing_symbols: string[]
  staleness_days: number | null
  health_level: 'healthy' | 'degraded' | 'down'
  coverage_ratio: number
  empty_ratio: number
  field_missing_ratio: number
  freshness_score: number
  last_success_at: string | null
  last_failure_at: string | null
  recent_failure_count: number
  recent_empty_count: number
  avg_latency_ms: number | null
  runtime_health_level: 'healthy' | 'degraded' | 'down' | 'unknown'
  notes: string[]
}

export interface MarketSourceHealthReport {
  status: 'healthy' | 'degraded' | 'empty'
  symbols: string[]
  start_date: string | null
  end_date: string | null
  adjustflag: string
  primary_source: string | null
  fallback_sources: string[]
  failover_policy: Record<string, unknown>
  sources: MarketSourceHealthItem[]
}

export async function fetchProviderCapabilities(): Promise<ProviderCapabilityMatrix> {
  const { data } = await apiClient.get('/market/providers/capabilities')
  return data
}

export async function fetchMarketSourceHealth(): Promise<MarketSourceHealthReport> {
  const { data } = await apiClient.get('/market/health/sources')
  return data
}
