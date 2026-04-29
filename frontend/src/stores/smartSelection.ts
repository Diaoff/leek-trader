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

const RUNNING_STATUSES = new Set(['queued', 'running'])
const POLL_INTERVAL_MS = 2000
const MAX_POLL_ROUNDS = 90

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
    pollingRunId: null as number | null,
    pollRoundsRemaining: 0,
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
        this.schedulePoll(result.run_id, MAX_POLL_ROUNDS)
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, '触发智能选股失败')
        this.clearPoll()
        this.running = false
      } finally {
        if (!this.pollTimer) {
          this.running = false
        }
      }
    },

    schedulePoll(runId: number, rounds: number) {
      this.clearPoll()
      if (rounds <= 0) {
        this.pollingRunId = null
        this.pollRoundsRemaining = 0
        this.running = false
        return
      }
      this.pollingRunId = runId
      this.pollRoundsRemaining = rounds
      this.running = true
      this.pollTimer = setTimeout(async () => {
        this.pollTimer = null
        try {
          await this.loadPage()
          const isTrackedTask = this.latestTask?.id === runId
          const status = isTrackedTask ? this.latestTask?.status : null
          if (status && RUNNING_STATUSES.has(status)) {
            this.schedulePoll(runId, rounds - 1)
            return
          }
          if (!isTrackedTask && rounds > 1) {
            this.schedulePoll(runId, rounds - 1)
            return
          }
          if (isTrackedTask && status === 'succeeded') {
            this.triggerMessage = `智能选股任务 #${runId} 已完成`
          } else if (isTrackedTask && status === 'failed') {
            this.triggerMessage = `智能选股任务 #${runId} 执行失败`
          }
          this.pollingRunId = null
          this.pollRoundsRemaining = 0
          this.running = false
        } catch (error: unknown) {
          this.error = getApiErrorMessage(error, '刷新智能选股任务状态失败')
          this.schedulePoll(runId, rounds - 1)
        }
      }, POLL_INTERVAL_MS)
    },

    clearPoll() {
      if (this.pollTimer) {
        clearTimeout(this.pollTimer)
        this.pollTimer = null
      }
      this.pollingRunId = null
      this.pollRoundsRemaining = 0
    },
  },
})
