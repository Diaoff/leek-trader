import { apiClient } from './client'
import type {
  CreateWatchlistGroupPayload,
  ReorderWatchlistGroupsPayload,
  UpdateWatchlistGroupPayload,
  WatchlistGroup,
} from '../types/watchlist'

export async function fetchWatchlistGroups(): Promise<WatchlistGroup[]> {
  const { data } = await apiClient.get('/watchlist-groups')
  return data
}

export async function createWatchlistGroup(payload: CreateWatchlistGroupPayload): Promise<WatchlistGroup> {
  const { data } = await apiClient.post('/watchlist-groups', payload)
  return data
}

export async function updateWatchlistGroup(groupId: number, payload: UpdateWatchlistGroupPayload): Promise<WatchlistGroup> {
  const { data } = await apiClient.patch(`/watchlist-groups/${groupId}`, payload)
  return data
}

export async function reorderWatchlistGroups(payload: ReorderWatchlistGroupsPayload): Promise<{ status: string }> {
  const { data } = await apiClient.post('/watchlist-groups/reorder', payload)
  return data
}

export async function deleteWatchlistGroup(groupId: number): Promise<{ status: string; id: number }> {
  const { data } = await apiClient.delete(`/watchlist-groups/${groupId}`)
  return data
}
