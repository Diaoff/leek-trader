import { apiClient } from './client'

export const fetchQuotes = async (symbols?: string[]) => {
  const params = symbols?.length ? { symbols } : undefined
  const { data } = await apiClient.get('/quotes', { params })
  return data
}
