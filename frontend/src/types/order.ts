export interface OrderItem {
  id: number
  tenant_id: string
  account_id: number
  symbol: string
  name: string | null
  side: 'buy' | 'sell'
  order_type: 'market' | 'limit'
  status: 'pending' | 'filled' | 'rejected' | 'cancelled'
  quantity: number
  price: string
  filled_quantity: number
  filled_price: string
  reject_reason: string | null
  risk_rule_version: string | null
}

export interface CreateOrderPayload {
  symbol: string
  side: 'buy' | 'sell'
  order_type: 'market' | 'limit'
  quantity: number
  price: number
  stop_loss_price?: number | null
  take_profit_price?: number | null
}

export interface CreateOrderResponse {
  status: 'accepted' | 'rejected'
  risk_rule_version?: string | null
  rejection_reason?: string
  order?: {
    id: number
    symbol: string
    name?: string | null
    quantity: number
    price: number
    status: string
    reject_reason?: string | null
  }
}

export interface CancelOrderResponse {
  status: 'accepted' | 'rejected' | 'not_found'
  message?: string
}

export interface MatchPendingOrdersResponse {
  status: 'accepted'
  matched_count: number
  matched_orders: Array<{
    id: number
    symbol: string
    name?: string | null
    status: string
    risk_rule_version: string | null
    filled_price: number
    filled_quantity: number
  }>
}

export type OrderStatus = OrderItem['status']
export type OrderSide = OrderItem['side']
export type OrderType = OrderItem['order_type']
