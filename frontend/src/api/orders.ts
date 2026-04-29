import { apiClient } from './client'
import type { OrderItem as SharedOrderItem } from '../types/order'

export interface CreateOrderPayload {
  symbol: string
  side: 'buy' | 'sell'
  order_type: 'market' | 'limit'
  quantity: number
  price: number
  stop_loss_price?: number | null
  take_profit_price?: number | null
}

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
}

export interface CreateOrderResponse {
  status: 'accepted' | 'rejected'
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
    filled_price: number
    filled_quantity: number
  }>
}

export async function fetchOrders(): Promise<SharedOrderItem[]> {
  const { data } = await apiClient.get('/orders')
  return data
}

export async function createOrder(payload: CreateOrderPayload): Promise<CreateOrderResponse> {
  const { data } = await apiClient.post('/orders', payload)
  return data
}

export async function cancelOrder(orderId: number): Promise<CancelOrderResponse> {
  const { data } = await apiClient.post(`/orders/${orderId}/cancel`)
  return data
}

export async function matchPendingOrders(): Promise<MatchPendingOrdersResponse> {
  const { data } = await apiClient.post('/orders/match-pending')
  return data
}
