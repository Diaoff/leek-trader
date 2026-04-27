import { apiClient } from './client'
import type { MarketOverview } from '../types/market'

export async function fetchMarketOverview(): Promise<MarketOverview> {
  const { data } = await apiClient.get('/market/overview')
  return data
}
