import { defineStore } from 'pinia'

import { fetchMarketOverview } from '../api/market'
import type { MarketOverview } from '../types/market'
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
    loading: false,
    error: '',
    lastUpdated: '未刷新',
  }),

  actions: {
    async loadMarketData() {
      this.loading = true
      this.error = ''

      try {
        this.overview = await fetchMarketOverview()
        this.lastUpdated = formatLocalTime(new Date().toISOString())
      } catch (error: unknown) {
        this.overview = null
        this.error = getApiErrorMessage(error, '市场概览加载失败')
      } finally {
        this.loading = false
      }
    },
  },
})
