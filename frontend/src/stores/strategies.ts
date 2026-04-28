import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import {
  createStrategy as createStrategyRequest,
  fetchLatestStrategyRun,
  fetchStrategyRunHistory,
  fetchStrategies,
  runStrategy,
  updateStrategy as updateStrategyRequest,
  type CreateStrategyPayload,
  type UpdateStrategyPayload,
} from '../api/strategies'
import type { StrategyItem, StrategyRunResult, StrategySignalAction } from '../types/strategy'

export const useStrategyStore = defineStore('strategies', {
  state: () => ({
    strategies: [] as StrategyItem[],
    lastRunResult: null as StrategyRunResult | null,
    runHistory: [] as StrategyRunResult[],
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

    async fetchLatestRun(strategyId?: number) {
      try {
        this.lastRunResult = await fetchLatestStrategyRun(strategyId)
        return this.lastRunResult
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略运行记录加载失败'
        throw error
      }
    },

    async fetchRunHistory(limit = 10, strategyId?: number) {
      try {
        const history = await fetchStrategyRunHistory(limit, strategyId)
        this.runHistory = history.runs
        return this.runHistory
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略运行日志加载失败'
        throw error
      }
    },

    async createStrategy(payload: CreateStrategyPayload) {
      this.loading = true
      this.error = ''

      try {
        const created = await createStrategyRequest(payload)
        await this.fetchStrategies()
        ElMessage.success('策略已创建')
        return created
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略创建失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateStrategy(strategyId: number, payload: UpdateStrategyPayload) {
      this.loading = true
      this.error = ''

      try {
        const updated = await updateStrategyRequest(strategyId, payload)
        await this.fetchStrategies()
        ElMessage.success('策略已更新')
        return updated
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略更新失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async setStrategyStatus(strategyId: number, status: 'active' | 'paused') {
      this.loading = true
      this.error = ''

      try {
        await updateStrategyRequest(strategyId, { status })
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
        this.lastRunResult = result
        await Promise.all([this.fetchStrategies(), this.fetchRunHistory()])
        ElMessage.success(this.buildRunMessage(result))
        return result
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : '策略运行失败'
        ElMessage.error(this.error)
        throw error
      } finally {
        this.loading = false
      }
    },

    buildRunMessage(result: StrategyRunResult) {
      if (result.order_submitted && result.side && result.quantity) {
        const sideLabel = result.side === 'buy' ? '买入' : '卖出'
        if (result.confirmation_source === 'special_attention_watchlist') {
          return `策略运行完成：重点关注放行，${sideLabel} ${result.quantity} 股`
        }
        return `策略运行完成：通过闸门并已下单，${sideLabel} ${result.quantity} 股`
      }

      if (result.reason === 'signal_only_mode') {
        return '策略运行完成：仅信号模式'
      }

      if (result.execution_blockers.includes('t_plus_one_restriction')) {
        return '策略运行完成：T+1 限制'
      }

      if (result.execution_blockers.includes('blocked_repeat_add')) {
        return '策略运行完成：最多允许一次补仓，超限已拦截'
      }

      if (result.execution_blockers.some((item) => item.startsWith('recommendation_'))) {
        return '策略运行完成：信号成立但未过推荐池'
      }

      if (result.execution_blockers.length > 0) {
        return '策略运行完成：信号成立但未执行'
      }

      return `策略运行完成：${this.signalLabel(result.signal.signal ?? 'hold')}`
    },

    signalLabel(signal: StrategySignalAction) {
      const mapping: Record<StrategySignalAction, string> = {
        buy: '买入',
        sell: '卖出',
        reduce: '减仓',
        hold: '观望',
      }
      return mapping[signal]
    },
  },
})
