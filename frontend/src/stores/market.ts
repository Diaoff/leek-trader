import { defineStore } from 'pinia'

import {
  fetchLatestMarketResearch,
  fetchMarketOverview,
  fetchMarketResearchHistory,
  runMarketResearch,
} from '../api/market'
import type { MarketOverview, MarketRecommendation, MarketResearchRun } from '../types/market'
import { getApiErrorMessage } from '../utils/http'

function formatLocalTime(value: string | null): string {
  if (!value) {
    return '未生成'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export const useMarketStore = defineStore('market', {
  state: () => ({
    overview: null as MarketOverview | null,
    recommendations: [] as MarketRecommendation[],
    snapshot: null as MarketResearchRun | null,
    latestTask: null as MarketResearchRun | null,
    history: [] as MarketResearchRun[],
    loading: false,
    reportLoading: false,
    running: false,
    error: '',
    triggerMessage: '',
    lastUpdated: '未刷新',
    pollTimer: null as ReturnType<typeof setTimeout> | null,
  }),

  actions: {
    async loadMarketData() {
      this.loading = true
      this.error = ''

      try {
        const [overviewResult, latestResult] = await Promise.allSettled([
          fetchMarketOverview(),
          fetchLatestMarketResearch(),
        ])

        const errors: string[] = []

        if (overviewResult.status === 'fulfilled') {
          this.overview = overviewResult.value
        } else {
          this.overview = null
          errors.push(getApiErrorMessage(overviewResult.reason, '市场概览加载失败'))
        }

        if (latestResult.status === 'fulfilled') {
          this.snapshot = latestResult.value.snapshot
          this.latestTask = latestResult.value.latest_task
          this.recommendations = latestResult.value.items
        } else {
          this.snapshot = null
          this.latestTask = null
          this.recommendations = []
          errors.push(getApiErrorMessage(latestResult.reason, '规则研究快照加载失败'))
        }

        this.error = errors.join('；')
        this.lastUpdated = formatLocalTime(new Date().toISOString())
      } finally {
        this.loading = false
      }
    },

    async loadResearchReport() {
      this.reportLoading = true
      this.error = ''

      try {
        const [latest, history] = await Promise.all([
          fetchLatestMarketResearch(),
          fetchMarketResearchHistory(),
        ])
        this.snapshot = latest.snapshot
        this.latestTask = latest.latest_task
        this.recommendations = latest.items
        this.history = history.runs
        this.lastUpdated = formatLocalTime(new Date().toISOString())
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, '研究报告加载失败')
      } finally {
        this.reportLoading = false
      }
    },

    async triggerResearchRun() {
      this.running = true
      this.triggerMessage = ''
      this.error = ''

      try {
        const result = await runMarketResearch()
        this.triggerMessage = `已提交研究任务 #${result.run_id}`
        await this.loadResearchReport()
        this.schedulePoll(4)
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, '触发规则研究失败')
      } finally {
        this.running = false
      }
    },

    schedulePoll(rounds: number) {
      this.clearPoll()
      if (rounds <= 0) {
        return
      }
      this.pollTimer = setTimeout(async () => {
        await this.loadResearchReport()
        const status = this.latestTask?.status
        if (status === 'queued' || status === 'running') {
          this.schedulePoll(rounds - 1)
        }
      }, 2000)
    },

    clearPoll() {
      if (this.pollTimer) {
        clearTimeout(this.pollTimer)
        this.pollTimer = null
      }
    },
  },
})
