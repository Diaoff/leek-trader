import { apiClient } from './client'

export interface CreateOrderPayload {
  symbol: string
  side: 'buy' | 'sell'
  order_type: 'market' | 'limit'
  quantity: number
  price: number
}

export interface OrderItem {
  id: number
  tenant_id: string
  account_id: number
  symbol: string
  side: 'buy' | 'sell'
  order_type: 'market' | 'limit'
  status: 'pending' | 'filled' | 'rejected' | 'cancelled'
  quantity: number
  price: string
  filled_quantity: number
  filled_price: string
  reject_reason: string | null
}

export async function fetchOrders(): Promise<OrderItem[]> {
  const { data } = await apiClient.get('/orders')
  return data
}

export async function createOrder(payload: CreateOrderPayload): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post('/orders', payload)
  return data
}

export async function cancelOrder(orderId: number): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post(`/orders/${orderId}/cancel`)
  return data
}

export async function matchPendingOrders(): Promise<Record<string, unknown>> {
  const { data } = await apiClient.post('/orders/match-pending')
  return data
}
