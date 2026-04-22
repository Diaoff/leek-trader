import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import { fetchAccounts } from '../api/accounts'
import { cancelOrder, createOrder, fetchOrders, matchPendingOrders } from '../api/orders'
import type { Account } from '../types/account'
import type { CreateOrderPayload, OrderItem } from '../types/order'

export const usePortfolioStore = defineStore('portfolio', {
  state: () => ({
    accounts: [] as Account[],
    positions: [] as Array<{
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
    }>,
    orders: [] as OrderItem[],
    summary: {
      total_equity: 0,
      available_cash: 0,
      frozen_cash: 0,
      market_value: 0,
      unrealized_pnl: 0,
    },
    loading: false,
    error: '',
  }),

  getters: {
    primaryAccount: (state) => state.accounts[0] ?? null,
    positionCount: (state) => state.positions.length,
    totalMarketValue: (state) => state.summary.market_value,
    totalEquity: (state) => state.summary.total_equity,
    availableCash: (state) => state.summary.available_cash,
    pendingOrders: (state) => state.orders.filter((o: OrderItem) => o.status === 'pending'),
    recentOrders: (state) => state.orders.slice(0, 5),
    orderCount: (state) => state.orders.length,
    pendingCount: (state) => state.orders.filter((o: OrderItem) => o.status === 'pending').length,
  },

  actions: {
    async fetchAccounts() {
      try {
        this.accounts = await fetchAccounts()
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '加载账户失败'
        throw error
      }
    },

    async fetchPositions() {
      try {
        const { fetchPositions: apiFetchPositions } = await import('../api/positions')
        this.positions = await apiFetchPositions()
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '加载持仓失败'
        throw error
      }
    },

    async fetchSummary() {
      try {
        const { fetchPortfolioSummary } = await import('../api/portfolio')
        this.summary = await fetchPortfolioSummary()
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '加载摘要失败'
        throw error
      }
    },

    async fetchOrders() {
      try {
        this.orders = await fetchOrders()
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '订单加载失败'
        throw error
      }
    },

    async loadAllPortfolioData() {
      this.loading = true
      this.error = ''

      try {
        await Promise.all([
          this.fetchAccounts(),
          this.fetchPositions(),
          this.fetchSummary(),
          this.fetchOrders(),
        ])
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '数据加载失败'
        throw error
      } finally {
        this.loading = false
      }
    },

    async submitOrder(payload: CreateOrderPayload) {
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
        await this.fetchPositions()
        await this.fetchSummary()
        return result
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '下单失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async cancelOrder(orderId: number) {
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
        await this.fetchPositions()
        await this.fetchSummary()
        return result
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '撤单失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async matchPendingOrders() {
      this.loading = true
      this.error = ''

      try {
        const result = await matchPendingOrders()
        ElMessage.success(`撮合完成，本次成交 ${result.matched_count} 笔挂单`)
        await this.fetchOrders()
        await this.fetchPositions()
        await this.fetchSummary()
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
