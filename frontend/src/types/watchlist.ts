export interface WatchlistItem {
  id: number
  tenant_id: string
  symbol: string
  group_id: number | null
  sort_order: number
  note: string | null
  is_pinned: boolean
  is_special_attention: boolean
  security_name: string
  security_code: string
  market: string
  tags: string[]
  created_at: string
}

export interface CreateWatchlistPayload {
  symbol: string
  group_id?: number | null
  note?: string | null
}

export interface UpdateWatchlistPayload {
  group_id?: number | null
  note?: string | null
  is_pinned?: boolean | null
  is_special_attention?: boolean | null
}

export interface ReorderWatchlistPayload {
  group_id: number
  pinned_ids: number[]
  regular_ids: number[]
}

export interface WatchlistGroup {
  id: number
  tenant_id: string
  name: string
  is_system: boolean
  sort_order: number
  item_count: number
  created_at: string
}

export interface CreateWatchlistGroupPayload {
  name: string
}

export interface UpdateWatchlistGroupPayload {
  name?: string
}

export interface ReorderWatchlistGroupsPayload {
  group_ids: number[]
}
