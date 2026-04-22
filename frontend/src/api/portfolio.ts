import { apiClient } from './client'

export interface PortfolioSummary {
  total_equity: number
  available_cash: number
  market_value: number
  unrealized_pnl: number
}

export async function fetchPortfolioSummary(): Promise<PortfolioSummary> {
  const { data } = await apiClient.get('/portfolio/summary')
  return data
}
