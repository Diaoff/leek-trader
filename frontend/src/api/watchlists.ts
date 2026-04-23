import { apiClient } from './client'
import type {
  CreateWatchlistPayload,
  ReorderWatchlistPayload,
  UpdateWatchlistPayload,
  WatchlistItem,
} from '../types/watchlist'

export async function fetchWatchlists(groupId?: number | null): Promise<WatchlistItem[]> {
  const { data } = await apiClient.get('/watchlists', {
    params: groupId ? { group_id: groupId } : undefined,
  })
  return data
}

export async function createWatchlist(payload: CreateWatchlistPayload): Promise<WatchlistItem> {
  const { data } = await apiClient.post('/watchlists', payload)
  return data
}

export async function updateWatchlist(itemId: number, payload: UpdateWatchlistPayload): Promise<WatchlistItem> {
  const { data } = await apiClient.patch(`/watchlists/${itemId}`, payload)
  return data
}

export async function reorderWatchlists(payload: ReorderWatchlistPayload): Promise<{ status: string }> {
  const { data } = await apiClient.post('/watchlists/reorder', payload)
  return data
}

export async function deleteWatchlist(itemId: number): Promise<{ status: string; id: number }> {
  const { data } = await apiClient.delete(`/watchlists/${itemId}`)
  return data
}
