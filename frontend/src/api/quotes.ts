import { apiClient } from './client'

export interface QuoteItem {
  symbol: string
  price: number
  change_percent: number
  volume: number
  timestamp: string
  is_halted: boolean
}

export const fetchQuotes = async (symbols?: string[]): Promise<QuoteItem[]> => {
  const params = symbols?.length ? { symbols } : undefined
  const { data } = await apiClient.get('/quotes', { params })
  return data
}
