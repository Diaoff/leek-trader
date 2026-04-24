import { apiClient } from './client'
import type {
  MarketOverview,
  MarketResearchHistory,
  MarketResearchLatest,
  MarketResearchRunDispatch,
} from '../types/market'

export async function fetchMarketOverview(): Promise<MarketOverview> {
  const { data } = await apiClient.get('/market/overview')
  return data
}

export async function fetchLatestMarketResearch(): Promise<MarketResearchLatest> {
  const { data } = await apiClient.get('/market/research/latest')
  return data
}

export async function fetchMarketResearchHistory(limit = 10): Promise<MarketResearchHistory> {
  const { data } = await apiClient.get('/market/research/history', { params: { limit } })
  return data
}

export async function runMarketResearch(): Promise<MarketResearchRunDispatch> {
  const { data } = await apiClient.post('/market/research/run')
  return data
}
