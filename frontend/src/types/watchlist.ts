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
