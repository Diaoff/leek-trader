import { defineStore } from 'pinia'

import {
  fetchLatestSmartSelection,
  fetchSmartSelectionConfig,
  fetchSmartSelectionHistory,
  runSmartSelection,
  updateSmartSelectionConfig,
} from '../api/smartSelection'
import type {
  SmartSelectionConfig,
  SmartSelectionItem,
  SmartSelectionRun,
} from '../types/smartSelection'
import { getApiErrorMessage } from '../utils/http'

function formatLocalTime(value: string | null): string {
  if (!value) {
    return '未刷新'
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

export const useSmartSelectionStore = defineStore('smartSelection', {
  state: () => ({
    config: null as SmartSelectionConfig | null,
    snapshot: null as SmartSelectionRun | null,
    latestTask: null as SmartSelectionRun | null,
    items: [] as SmartSelectionItem[],
    history: [] as SmartSelectionRun[],
    loading: false,
    saving: false,
    running: false,
    error: '',
    triggerMessage: '',
    lastUpdated: '未刷新',
    pollTimer: null as ReturnType<typeof setTimeout> | null,
  }),

  actions: {
    async loadPage() {
      this.loading = true
      this.error = ''

      try {
        const [config, latest, history] = await Promise.all([
          fetchSmartSelectionConfig(),
          fetchLatestSmartSelection(),
          fetchSmartSelectionHistory(),
        ])
        this.config = config
        this.snapshot = latest.snapshot
        this.latestTask = latest.latest_task
        this.items = latest.items
        this.history = history.runs
        this.lastUpdated = formatLocalTime(new Date().toISOString())
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, '智能选股页面加载失败')
      } finally {
        this.loading = false
      }
    },

    async saveEnabled(enabled: boolean) {
      this.saving = true
      this.error = ''

      try {
        this.config = await updateSmartSelectionConfig({ enabled })
        this.lastUpdated = formatLocalTime(new Date().toISOString())
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, '基础偏好保存失败')
        throw error
      } finally {
        this.saving = false
      }
    },

    async triggerRun() {
      this.running = true
      this.triggerMessage = ''
      this.error = ''

      try {
        const result = await runSmartSelection()
        this.triggerMessage = `已提交智能选股任务 #${result.run_id}`
        await this.loadPage()
        this.schedulePoll(5)
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, '触发智能选股失败')
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
        await this.loadPage()
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
