import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import {
  cancelOrder,
  createOrder,
  fetchOrders,
  matchPendingOrders,
} from '../api/orders'
import type { CancelOrderResponse, CreateOrderPayload, CreateOrderResponse, MatchPendingOrdersResponse, OrderItem } from '../types/order'

export const useOrderStore = defineStore('orders', {
  state: () => ({
    orders: [] as OrderItem[],
    loading: false,
    error: '',
  }),

  getters: {
    pendingOrders: (state) => state.orders.filter((o: OrderItem) => o.status === 'pending'),
    recentOrders: (state) => state.orders.slice(0, 5),
    orderCount: (state) => state.orders.length,
    pendingCount: (state) => state.orders.filter((o: OrderItem) => o.status === 'pending').length,
  },

  actions: {
    async fetchOrders() {
      this.loading = true
      this.error = ''

      try {
        this.orders = await fetchOrders()
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '订单加载失败'
        throw error
      } finally {
        this.loading = false
      }
    },

    async submitOrder(payload: CreateOrderPayload): Promise<CreateOrderResponse> {
      this.loading = true
      this.error = ''

      try {
        const result = await createOrder(payload)

        if (result.status === 'rejected') {
          const message = `下单失败：${result.rejection_reason ?? '未知原因'}`
          ElMessage.warning(message)
        } else if (result.order?.status === 'pending') {
          ElMessage.success('挂单已创建')
        } else {
          ElMessage.success('订单已提交并完成处理')
        }

        await this.fetchOrders()
        return result
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '下单失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async cancelOrder(orderId: number): Promise<CancelOrderResponse> {
      this.loading = true
      this.error = ''

      try {
        const result = await cancelOrder(orderId)

        if (result.status === 'accepted') {
          ElMessage.success('撤单成功')
        } else {
          const message = result.message ?? '撤单失败'
          ElMessage.warning(message)
        }

        await this.fetchOrders()
        return result
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '撤单失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async matchPendingOrders(): Promise<MatchPendingOrdersResponse> {
      this.loading = true
      this.error = ''

      try {
        const result = await matchPendingOrders()
        ElMessage.success(`撮合完成，本次成交 ${result.matched_count} 笔挂单`)
        await this.fetchOrders()
        return result
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '挂单撮合失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },
  },
})
