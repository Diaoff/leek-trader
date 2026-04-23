import { apiClient } from './client'

export interface SecuritySearchResult {
  symbol: string
  code: string
  name: string
  market: string
  pinyin_abbr: string
  tags: string[]
}

export async function searchSecurities(query: string): Promise<SecuritySearchResult[]> {
  const { data } = await apiClient.get('/securities/search', {
    params: { q: query },
  })
  return data
}
