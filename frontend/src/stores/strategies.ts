import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import { fetchStrategies, runStrategy, updateStrategy } from '../api/strategies'
import type { StrategyItem } from '../types/strategy'

export const useStrategyStore = defineStore('strategies', {
  state: () => ({
    strategies: [] as StrategyItem[],
    loading: false,
    error: '',
  }),

  getters: {
    activeStrategies: (state) => state.strategies.filter((strategy) => strategy.status === 'active'),
    strategyCount: (state) => state.strategies.length,
  },

  actions: {
    async fetchStrategies() {
      this.loading = true
      this.error = ''

      try {
        this.strategies = await fetchStrategies()
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略数据加载失败'
        this.strategies = []
        throw error
      } finally {
        this.loading = false
      }
    },

    async setStrategyStatus(strategyId: number, status: 'active' | 'paused') {
      this.loading = true
      this.error = ''

      try {
        await updateStrategy(strategyId, { status })
        await this.fetchStrategies()
        ElMessage.success(status === 'active' ? '策略已启用' : '策略已暂停')
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略状态更新失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async runStrategy(strategyId: number) {
      this.loading = true
      this.error = ''

      try {
        const result = await runStrategy(strategyId)
        await this.fetchStrategies()
        ElMessage.success(`策略运行完成：${result.signal.signal ?? 'hold'}`)
        return result
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略运行失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },
  },
})
