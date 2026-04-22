import { apiClient } from './client'

export interface WatchlistItem {
  id: number
  tenant_id: string
  symbol: string
  sort_order: number
  created_at: string
}

export interface CreateWatchlistPayload {
  symbol: string
}

export async function fetchWatchlists(): Promise<WatchlistItem[]> {
  const { data } = await apiClient.get('/watchlists')
  return data
}

export async function createWatchlist(payload: CreateWatchlistPayload): Promise<WatchlistItem> {
  const { data } = await apiClient.post('/watchlists', payload)
  return data
}

export async function deleteWatchlist(itemId: number): Promise<{ status: string; id: number }> {
  const { data } = await apiClient.delete(`/watchlists/${itemId}`)
  return data
}
