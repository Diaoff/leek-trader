import { defineStore } from 'pinia'

import { fetchStrategies } from '../api/strategies'
import type { StrategyItem } from '../types/strategy'

export const useStrategyStore = defineStore('strategies', {
  state: () => ({
    strategies: [] as Array<StrategyItem & {
      todaySignals: number
      todayProfit: number
      totalReturn: number
    }>,
    loading: false,
    error: '',
  }),

  getters: {
    activeStrategies: (state) => state.strategies.filter((s) => s.status === 'active'),
    strategyCount: (state) => state.strategies.length,
  },

  actions: {
    async fetchStrategies() {
      this.loading = true
      this.error = ''

      try {
        const strategies = await fetchStrategies()
        // Add mock data for the enhanced features
        this.strategies = strategies.map((strategy) => ({
          ...strategy,
          todaySignals: strategy.status === 'active' ? Math.floor(Math.random() * 10) : 0,
          todayProfit: strategy.status === 'active' ? Number((Math.random() * 5 - 1).toFixed(2)) : 0,
          totalReturn: Number((Math.random() * 20 - 2).toFixed(2)),
        }))
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略数据加载失败'
        this.strategies = []
        throw error
      } finally {
        this.loading = false
      }
    },
  },
})
