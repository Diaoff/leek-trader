import { apiClient } from './client'

export interface MarketDataQualitySymbolReport {
  symbol: string
  rows: number
  first_trade_date: string | null
  last_trade_date: string | null
  suspended_rows: number
  st_rows: number
  null_counts: Record<string, number>
  calendar_gap_days: string[]
}

export interface MarketDataQualityReport {
  status: string
  source: string
  adjustflag: string
  symbols: string[]
  start_date: string | null
  end_date: string | null
  total_rows: number
  field_count: number
  nullable_fields: string[]
  symbol_reports: MarketDataQualitySymbolReport[]
}

export async function fetchDailyBarQuality(symbols: string[]): Promise<MarketDataQualityReport> {
  const { data } = await apiClient.post('/market/quality/daily-bars', {
    symbols,
    source: 'baostock',
    adjustflag: '2',
  })
  return data
}
