import { apiClient } from './client'

export interface QuoteItem {
  symbol: string
  name: string | null
  price: number
  change_percent: number
  volume: number
  timestamp: string
  is_halted: boolean
  market_cap: number | null
  ytd_change_percent: number | null
}

export const fetchQuotes = async (symbols?: string[]): Promise<QuoteItem[]> => {
  const params = symbols?.length ? { symbols } : undefined
  const { data } = await apiClient.get('/quotes', {
    params,
    paramsSerializer: {
      indexes: null,
    },
  })
  return data
}
