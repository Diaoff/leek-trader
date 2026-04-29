export interface QuoteItem {
  symbol: string
  name: string | null
  price: number
  change_percent: number
  volume: number
  timestamp: string
  is_halted: boolean
}
