import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import { fetchStrategies } from '../api/strategies'
import type { StrategyItem } from '../types/strategy'

export const useStrategyStore = defineStore('strategies', {
  state: () => ({
    strategies: [] as Array<StrategyItem & {
      todaySignals: number
      todayProfit: number
      totalReturn: number
    }>,
    strategyStats: {
      total: 8,
      running: 3,
      todaySignals: 12,
      totalReturn: 15.8,
    },
    editingStrategy: {
      id: null as number | null,
      name: '',
      type: 'ma' as 'ma' | 'macd' | 'rsi' | 'boll' | 'grid',
      shortPeriod: 5,
      longPeriod: 20,
      stockCode: '600519',
      positionRatio: 0.1,
    },
    showConfigModal: false,
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
          todayProfit: strategy.status === 'active' ? (Math.random() * 5 - 1).toFixed(2) : 0,
          totalReturn: (Math.random() * 20 - 2).toFixed(2),
        }))
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略数据加载失败'
        this.strategies = []
        throw error
      } finally {
        this.loading = false
      }
    },

    editStrategy(strategy: typeof this.strategies[0]) {
      this.editingStrategy = {
        id: strategy.id,
        name: strategy.name,
        type: strategy.strategy_type as 'ma' | 'macd' | 'rsi' | 'boll' | 'grid',
        shortPeriod: 5,
        longPeriod: 20,
        stockCode: strategy.signal_symbol,
        positionRatio: 0.1,
      }
      this.showConfigModal = true
    },

    toggleStrategy(strategy: typeof this.strategies[0], action: 'start' | 'stop') {
      strategy.status = action === 'start' ? 'active' : 'inactive'
      ElMessage.success(`${action === 'start' ? '启动' : '停止'}策略成功`)
    },

    deleteStrategy(strategy: typeof this.strategies[0]) {
      if (confirm(`确定要删除策略"${strategy.name}"吗？`)) {
        const index = this.strategies.findIndex(s => s.id === strategy.id)
        if (index > -1) {
          this.strategies.splice(index, 1)
          ElMessage.success('策略已删除')
        }
      }
    },

    saveStrategy() {
      if (this.editingStrategy.id) {
        const index = this.strategies.findIndex(s => s.id === this.editingStrategy.id)
        if (index > -1) {
          this.strategies[index] = {
            ...this.strategies[index],
            name: this.editingStrategy.name,
            strategy_type: this.editingStrategy.type,
            signal_symbol: this.editingStrategy.stockCode,
          }
          ElMessage.success('策略已更新')
        }
      } else {
        const newStrategy = {
          id: Date.now(),
          tenant_id: 'default',
          name: this.editingStrategy.name,
          strategy_type: this.editingStrategy.type,
          status: 'inactive' as const,
          parameters: {
            short_period: this.editingStrategy.shortPeriod,
            long_period: this.editingStrategy.longPeriod,
            position_ratio: this.editingStrategy.positionRatio,
          },
          latest_signal: 'hold',
          signal_symbol: this.editingStrategy.stockCode,
          todaySignals: 0,
          todayProfit: 0,
          totalReturn: 0,
        }
        this.strategies.push(newStrategy)
        ElMessage.success('策略已创建')
      }
      this.showConfigModal = false
    },

    openConfigModal() {
      this.editingStrategy = {
        id: null,
        name: '',
        type: 'ma',
        shortPeriod: 5,
        longPeriod: 20,
        stockCode: '600519',
        positionRatio: 0.1,
      }
      this.showConfigModal = true
    },
  },
})
