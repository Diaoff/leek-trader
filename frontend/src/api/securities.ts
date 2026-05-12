import { apiClient } from './client'

export interface SecuritySearchResult {
  symbol: string
  code: string
  name: string
  market: string
  pinyin_abbr: string
  tags: string[]
}

export interface SecurityScreenResult extends SecuritySearchResult {
  in_watchlist: boolean
  market_cap: number | null
  price: number | null
  change_percent: number | null
}

export interface SecurityScreenParams {
  market?: string | null
  q?: string | null
  exclude_st?: boolean
  tags?: string[]
  min_market_cap?: number | null
  max_market_cap?: number | null
  limit?: number
}

export async function searchSecurities(query: string): Promise<SecuritySearchResult[]> {
  const { data } = await apiClient.get('/securities/search', {
    params: { q: query },
  })
  return data
}

export async function screenSecurities(params: SecurityScreenParams = {}): Promise<SecurityScreenResult[]> {
  const { data } = await apiClient.get('/securities/screen', {
    params,
    paramsSerializer: {
      indexes: null,
    },
  })
  return data
}
