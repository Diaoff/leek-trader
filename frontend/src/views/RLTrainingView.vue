<template>
  <section class="space-y-4">
    <PageHeader
      title="RL 训练台"
      subtitle="配置训练范围、生成日线强化学习模型，并管理模型验证状态。"
    />

    <ErrorAlert :message="error" />
    <SuccessAlert :message="successMessage" />

    <div class="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">训练配置</h3>
            <p class="panel-subtitle">第一版使用可解释的 Q-learning 分桶模型；训练产物保存在本地文件型模型注册表。</p>
          </div>
          <span class="status-chip subtle">{{ resolvedSymbols.length }} 只标的</span>
        </div>

        <form class="space-y-4" @submit.prevent="submitTraining">
          <div>
            <label class="field-label" for="model-name">模型名称</label>
            <input id="model-name" v-model.trim="form.modelName" class="field-input" type="text" placeholder="例如 重点关注池 RL 日线模型" />
          </div>

          <div>
            <div class="field-label">训练范围</div>
            <div class="grid gap-2 md:grid-cols-2">
              <button
                v-for="scope in scopeOptions"
                :key="scope.key"
                type="button"
                :class="['rounded-[18px] border p-4 text-left transition', form.scope === scope.key ? 'border-cyan-300/50 bg-cyan-300/[0.12]' : 'border-white/5 bg-white/[0.03] hover:bg-white/[0.06]']"
                @click="selectScope(scope.key)"
              >
                <div class="font-semibold text-[var(--text-primary)]">{{ scope.label }}</div>
                <div class="mt-1 text-xs text-[var(--text-tertiary)]">{{ scope.description }}</div>
              </button>
            </div>
          </div>

          <div v-if="form.scope === 'manual'">
            <label class="field-label" for="manual-symbols">手动股票代码</label>
            <textarea
              id="manual-symbols"
              v-model="form.manualSymbols"
              class="field-input min-h-24"
              placeholder="每行或逗号分隔，例如 sh600519, sz300750"
            />
          </div>

          <div class="grid gap-3 md:grid-cols-3">
            <div>
              <label class="field-label" for="start-date">开始日期</label>
              <input id="start-date" v-model="form.startDate" class="field-input mono-data" type="date" />
            </div>
            <div>
              <label class="field-label" for="end-date">结束日期</label>
              <input id="end-date" v-model="form.endDate" class="field-input mono-data" type="date" />
            </div>
            <div>
              <label class="field-label" for="limit">标的上限</label>
              <input id="limit" v-model.number="form.limit" class="field-input mono-data" type="number" min="1" max="300" step="1" />
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-3">
            <div>
              <label class="field-label" for="episodes">训练轮数</label>
              <input id="episodes" v-model.number="form.episodes" class="field-input mono-data" type="number" min="1" max="500" step="1" />
            </div>
            <div>
              <label class="field-label" for="learning-rate">学习率</label>
              <input id="learning-rate" v-model.number="form.learningRate" class="field-input mono-data" type="number" min="0.01" max="1" step="0.01" />
            </div>
            <div>
              <label class="field-label" for="exploration-rate">探索率</label>
              <input id="exploration-rate" v-model.number="form.explorationRate" class="field-input mono-data" type="number" min="0" max="1" step="0.01" />
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-3">
            <div>
              <label class="field-label" for="initial-cash">初始资金</label>
              <input id="initial-cash" v-model.number="form.initialCash" class="field-input mono-data" type="number" min="1000" step="1000" />
            </div>
            <div>
              <label class="field-label" for="max-position">最大仓位</label>
              <input id="max-position" v-model.number="form.maxPositionPct" class="field-input mono-data" type="number" min="0" max="1" step="0.05" />
            </div>
            <div>
              <label class="field-label" for="reward-mode">奖励模式</label>
              <select id="reward-mode" v-model="form.rewardMode" class="field-select">
                <option value="net_worth_change">净值变化</option>
                <option value="excess_return">超额收益</option>
                <option value="drawdown_penalty">回撤惩罚</option>
              </select>
            </div>
          </div>

          <div class="flex flex-wrap gap-3">
            <button class="secondary-button" type="button" :disabled="loading" @click="resolveSymbols">预览范围</button>
            <button class="primary-button" type="submit" :disabled="loading || !canTrain">
              {{ loading ? '训练中...' : '开始训练' }}
            </button>
          </div>

          <div v-if="currentJob" class="rounded-[18px] border border-cyan-300/10 bg-cyan-300/[0.06] p-4">
            <div class="flex items-center justify-between gap-3 text-sm">
              <div>
                <div class="font-semibold text-[var(--text-primary)]">训练进度：{{ jobStatusLabel(currentJob.status) }}</div>
                <div class="mono-data mt-1 text-xs text-[var(--text-tertiary)]">{{ currentJob.job_id }}</div>
              </div>
              <span class="status-chip subtle">{{ progressPercent(currentJob.progress_pct) }}%</span>
            </div>
            <div class="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
              <div class="h-full rounded-full bg-cyan-300 transition-all" :style="{ width: `${progressPercent(currentJob.progress_pct)}%` }" />
            </div>
            <div class="mt-2 flex items-center justify-between gap-3 text-xs text-[var(--text-tertiary)]">
              <span>{{ currentJob.progress_label || '等待进度更新' }}</span>
              <span class="mono-data">{{ currentJob.progress_step }} / {{ currentJob.progress_total }}</span>
            </div>
          </div>
        </form>
      </div>

      <div class="space-y-4">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">范围预览</h3>
              <p class="panel-subtitle">训练前确认标的来源和名称。</p>
            </div>
            <span class="status-chip subtle">{{ resolvedSymbols.length }}</span>
          </div>
          <div v-if="resolvedSymbols.length === 0" class="compact-empty">尚未解析训练范围</div>
          <div v-else class="space-y-2">
            <div v-for="item in resolvedSymbols.slice(0, 12)" :key="item.symbol" class="flex items-center justify-between gap-3 rounded-[14px] border border-white/5 bg-white/[0.03] px-3 py-2 text-sm">
              <span>{{ formatSecurityDisplay(item) }}</span>
              <span class="status-chip subtle">{{ item.source }}</span>
            </div>
            <div v-if="resolvedSymbols.length > 12" class="text-xs text-[var(--text-tertiary)]">其余 {{ resolvedSymbols.length - 12 }} 只已折叠。</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3 class="panel-title">最新训练结果</h3>
              <p class="panel-subtitle">训练完成后会显示模型 ID、交易次数和平均收益。</p>
            </div>
          </div>
          <div v-if="!latestModel" class="compact-empty">暂无本次训练结果</div>
          <div v-else class="space-y-3 text-sm">
            <div class="flex items-center justify-between gap-3">
              <span class="muted-text">模型</span>
              <span class="mono-data">{{ latestModel.model_id }}</span>
            </div>
            <div class="flex items-center justify-between gap-3">
              <span class="muted-text">状态</span>
              <span class="status-chip positive">{{ statusLabel(latestModel.status) }}</span>
            </div>
            <div class="grid grid-cols-3 gap-3">
              <MetricCard label="标的数" :value="String(metricValue(latestModel.metrics.evaluated_symbol_count))" />
              <MetricCard label="交易次数" :value="String(metricValue(latestModel.metrics.trade_count))" />
              <MetricCard label="平均收益" :value="`${metricValue(latestModel.metrics.avg_total_return_pct)}%`" />
            </div>
            <div v-if="validationBlockers(latestModel).length > 0" class="rounded-[14px] border border-amber-300/20 bg-amber-300/[0.08] p-3 text-xs text-amber-100">
              <div class="font-semibold">验证未完全通过</div>
              <div v-for="blocker in validationBlockers(latestModel)" :key="blocker" class="mt-1">{{ blocker }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">模型注册表</h3>
          <p class="panel-subtitle">本地已保存的 RL 模型，可用于后续接入策略推理。</p>
        </div>
        <button class="secondary-button" type="button" @click="loadModels">刷新</button>
      </div>

      <div v-if="models.length === 0" class="compact-empty">暂无模型</div>
      <div v-else class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>模型</th>
              <th>范围</th>
              <th>状态</th>
              <th>收益</th>
              <th>交易</th>
              <th>验证</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="model in models" :key="model.model_id">
              <td>
                <div class="font-semibold">{{ model.name }}</div>
                <div class="mono-data muted-text mt-1">{{ model.model_id }}</div>
              </td>
              <td>{{ scopeLabel(model.scope) }} · {{ model.symbols.length }} 只</td>
              <td><span class="status-chip subtle">{{ statusLabel(model.status) }}</span></td>
              <td class="mono-data">{{ metricValue(model.metrics.avg_total_return_pct) }}%</td>
              <td class="mono-data">{{ metricValue(model.metrics.trade_count) }}</td>
              <td>
                <span :class="['status-chip', validationPassed(model) ? 'positive' : 'subtle']">{{ validationPassed(model) ? '通过' : '需复核' }}</span>
                <div v-if="validationBlockers(model).length > 0" class="mt-1 text-xs text-[var(--text-tertiary)]">{{ validationBlockers(model)[0] }}</div>
              </td>
              <td class="mono-data">{{ formatDateTime(model.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import ErrorAlert from '../components/ErrorAlert.vue'
import MetricCard from '../components/MetricCard.vue'
import PageHeader from '../components/PageHeader.vue'
import SuccessAlert from '../components/SuccessAlert.vue'
import { fetchRLModels, fetchRLTrainingJob, fetchRLTrainingScopes, resolveRLTrainingSymbols, submitRLTrainingJob } from '../api/market'
import type { RLModelArtifact, RLTrainingJob, RLTrainingScope, RLTrainingScopeOption, RLTrainingSymbol } from '../types/rlTraining'
import { formatDateTime as formatApiDateTime } from '../utils/format'
import { getApiErrorMessage } from '../utils/http'
import { formatSecurityDisplay } from '../utils/securityDisplay'

const loading = ref(false)
const error = ref('')
const successMessage = ref('')
const scopeOptions = ref<RLTrainingScopeOption[]>([])
const resolvedSymbols = ref<RLTrainingSymbol[]>([])
const models = ref<RLModelArtifact[]>([])
const latestModel = ref<RLModelArtifact | null>(null)
const currentJob = ref<RLTrainingJob | null>(null)
let pollTimer: number | null = null

const form = reactive({
  modelName: 'RL 日线模型',
  scope: 'watchlist' as RLTrainingScope,
  manualSymbols: '',
  startDate: '',
  endDate: '',
  limit: 50,
  episodes: 25,
  learningRate: 0.2,
  explorationRate: 0.1,
  initialCash: 100000,
  maxPositionPct: 1,
  rewardMode: 'net_worth_change' as 'net_worth_change' | 'excess_return' | 'drawdown_penalty',
})

const canTrain = computed(() => form.modelName.trim().length > 0)

onMounted(async () => {
  await Promise.all([loadScopes(), loadModels()])
})

onBeforeUnmount(() => {
  stopPolling()
})

function manualSymbols(): string[] {
  return form.manualSymbols
    .split(/[\n,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function selectScope(scope: RLTrainingScope): void {
  form.scope = scope
  resolvedSymbols.value = []
}

async function loadScopes(): Promise<void> {
  const payload = await fetchRLTrainingScopes()
  scopeOptions.value = payload.scopes
}

async function loadModels(): Promise<void> {
  const payload = await fetchRLModels()
  models.value = payload.models
}

async function resolveSymbols(): Promise<void> {
  error.value = ''
  try {
    const payload = await resolveRLTrainingSymbols({
      scope: form.scope,
      symbols: manualSymbols(),
      limit: form.limit,
    })
    resolvedSymbols.value = payload.symbols
  } catch (err: unknown) {
    error.value = getApiErrorMessage(err, '训练范围解析失败')
  }
}

async function submitTraining(): Promise<void> {
  loading.value = true
  error.value = ''
  successMessage.value = ''
  latestModel.value = null
  stopPolling()
  try {
    const job = await submitRLTrainingJob({
      model_name: form.modelName.trim(),
      scope: form.scope,
      symbols: manualSymbols(),
      start_date: form.startDate || null,
      end_date: form.endDate || null,
      limit: form.limit,
      episodes: form.episodes,
      learning_rate: form.learningRate,
      exploration_rate: form.explorationRate,
      initial_cash: form.initialCash,
      max_position_pct: form.maxPositionPct,
      reward_mode: form.rewardMode,
    })
    currentJob.value = job
    successMessage.value = `训练任务已提交：${job.job_id}`
    startPolling(job.job_id)
  } catch (err: unknown) {
    loading.value = false
    error.value = getApiErrorMessage(err, 'RL 模型训练任务提交失败')
  }
}

function startPolling(jobId: string): void {
  stopPolling()
  void refreshJob(jobId)
  pollTimer = window.setInterval(() => {
    void refreshJob(jobId)
  }, 1200)
}

function stopPolling(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function refreshJob(jobId: string): Promise<void> {
  try {
    const job = await fetchRLTrainingJob(jobId)
    currentJob.value = job
    if (job.status === 'succeeded') {
      stopPolling()
      loading.value = false
      if (job.model) {
        latestModel.value = job.model
        resolvedSymbols.value = job.model.symbols
        successMessage.value = `训练完成：${job.model.name}`
      } else {
        successMessage.value = '训练完成'
      }
      await loadModels()
    } else if (job.status === 'failed') {
      stopPolling()
      loading.value = false
      error.value = job.error || 'RL 模型训练失败'
    }
  } catch (err: unknown) {
    stopPolling()
    loading.value = false
    error.value = getApiErrorMessage(err, '训练进度刷新失败')
  }
}

function metricValue(value: unknown): string | number {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? value : value.toFixed(2)
  }
  if (typeof value === 'string') {
    return value
  }
  return '--'
}

function statusLabel(status: string): string {
  const mapping: Record<string, string> = {
    draft: '草稿',
    validated: '已验证',
    active: '启用',
    retired: '退役',
  }
  return mapping[status] ?? status
}

function scopeLabel(scope: string): string {
  return scopeOptions.value.find((item) => item.key === scope)?.label ?? scope
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return '--'
  }
  return formatApiDateTime(value)
}
function jobStatusLabel(status: string): string {
  const mapping: Record<string, string> = {
    queued: '排队中',
    running: '运行中',
    succeeded: '已完成',
    failed: '失败',
  }
  return mapping[status] ?? status
}

function progressPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }
  return Math.min(100, Math.max(0, Math.round(value)))
}

function validationPassed(model: RLModelArtifact): boolean {
  return Boolean((model.validation as { passed?: unknown } | undefined)?.passed)
}

function validationBlockers(model: RLModelArtifact): string[] {
  const blockers = (model.validation as { blockers?: unknown } | undefined)?.blockers
  return Array.isArray(blockers) ? blockers.filter((item): item is string => typeof item === 'string') : []
}
</script>
