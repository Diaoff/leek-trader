export interface PositionItem {
  id: number
  tenant_id: string
  account_id: number
  symbol: string
  market: string
  quantity: number
  available_quantity: number
  average_cost: string
  last_price: string
  unrealized_pnl: string
  realized_pnl: string
}
