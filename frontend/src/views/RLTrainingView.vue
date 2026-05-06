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
              <p class="panel-subtitle">默认使用 PPO + 样本外验证；训练产物保存在本地文件型模型注册表。</p>
          </div>
          <span class="status-chip subtle">{{ resolvedSymbols.length }} 只标的</span>
        </div>

        <form class="space-y-4" @submit.prevent="submitTraining">
          <div class="grid gap-3 md:grid-cols-2">
            <div>
              <label class="field-label" for="model-name">模型名称</label>
              <input id="model-name" v-model.trim="form.modelName" class="field-input" type="text" placeholder="例如 重点关注池 RL 日线模型" />
            </div>
            <div>
              <label class="field-label" for="algorithm">训练算法</label>
              <select id="algorithm" v-model="form.algorithm" class="field-select">
                <option value="ppo_trading">PPO 深度训练模型</option>
              </select>
            </div>
          </div>

          <div>
            <div class="field-label">训练范围</div>
            <div class="grid gap-2 md:grid-cols-2">
              <button
                v-for="scope in scopeOptions"
                :key="scope.key"
                type="button"
                :class="['rounded-[18px] border p-4 text-left transition', form.scopes.includes(scope.key) ? 'border-cyan-300/50 bg-cyan-300/[0.12]' : 'border-white/5 bg-white/[0.03] hover:bg-white/[0.06]']"
                @click="toggleScope(scope.key)"
              >
                <div class="font-semibold text-[var(--text-primary)]">{{ scope.label }}</div>
                <div class="mt-1 text-xs text-[var(--text-tertiary)]">{{ scope.description }}</div>
              </button>
            </div>
          </div>

          <div v-if="form.scopes.includes('manual')">
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
              <label class="field-label" for="total-timesteps">训练步数</label>
              <input id="total-timesteps" v-model.number="form.totalTimesteps" class="field-input mono-data" type="number" min="1000" max="2000000" step="1000" />
            </div>
            <div>
              <label class="field-label" for="train-split">训练切分</label>
              <input id="train-split" v-model.number="form.trainSplitPct" class="field-input mono-data" type="number" min="0.5" max="0.95" step="0.05" />
            </div>
            <div>
              <label class="field-label" for="ppo-learning-rate">PPO 学习率</label>
              <input id="ppo-learning-rate" v-model.number="form.ppoLearningRate" class="field-input mono-data" type="number" min="0.00001" max="0.01" step="0.0001" />
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-2">
            <div>
              <label class="field-label" for="ppo-n-steps">Rollout 步数</label>
              <input id="ppo-n-steps" v-model.number="form.ppoNSteps" class="field-input mono-data" type="number" min="64" max="8192" step="64" />
            </div>
            <div>
              <label class="field-label" for="ppo-batch-size">Batch Size</label>
              <input id="ppo-batch-size" v-model.number="form.ppoBatchSize" class="field-input mono-data" type="number" min="16" max="2048" step="16" />
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
                <option value="risk_adjusted_excess_return">风险调整超额收益</option>
                <option value="net_worth_change">净值变化（兼容）</option>
                <option value="excess_return">超额收益</option>
                <option value="drawdown_penalty">回撤惩罚（稳健偏低频；已加入最低参与激励）</option>
              </select>
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-3">
            <div>
              <label class="field-label" for="drawdown-penalty">回撤惩罚</label>
              <input id="drawdown-penalty" v-model.number="form.drawdownPenaltyCoef" class="field-input mono-data" type="number" min="0" max="1" step="0.005" />
            </div>
            <div>
              <label class="field-label" for="turnover-penalty">换手惩罚</label>
              <input id="turnover-penalty" v-model.number="form.turnoverPenaltyCoef" class="field-input mono-data" type="number" min="0" max="1" step="0.0005" />
            </div>
            <div>
              <label class="field-label" for="min-validation-bars">最小验证 Bar</label>
              <input id="min-validation-bars" v-model.number="form.minValidationBars" class="field-input mono-data" type="number" min="1" max="252" step="1" />
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
            <div v-if="currentSyncSymbol(currentJob)" class="mt-3 rounded-[12px] border border-cyan-300/15 bg-cyan-300/[0.08] px-3 py-2 text-xs text-[var(--text-primary)]">
              正在同步：<span class="mono-data text-cyan-100">{{ currentSyncSymbol(currentJob) }}</span>
            </div>
            <div v-if="progressDetails(currentJob).length" class="mt-3 grid gap-1 text-xs text-[var(--text-secondary)]">
              <div
                v-for="detail in progressDetails(currentJob)"
                :key="detail"
                class="rounded-[10px] border border-white/5 bg-black/10 px-2 py-1"
              >
                {{ detail }}
              </div>
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
            <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
              <MetricCard label="候选标的" :value="String(metricValue(latestModel.metrics.candidate_symbol_count ?? latestModel.metrics.evaluated_symbol_count))" />
              <MetricCard label="可训练标的" :value="String(metricValue(latestModel.metrics.trainable_symbol_count ?? latestModel.metrics.evaluated_symbol_count))" />
              <MetricCard label="覆盖率" :value="percentMetric(latestModel.metrics.trainable_symbol_ratio)" />
              <MetricCard label="状态转移" :value="String(metricValue(latestModel.metrics.training_transition_count ?? latestModel.training.transitions))" />
              <MetricCard label="验证交易" :value="String(metricValue(latestModel.metrics.validation_trade_count ?? latestModel.metrics.trade_count))" />
              <MetricCard label="验证收益" :value="`${metricValue(validationMetric(latestModel, 'avg_total_return_pct') ?? latestModel.metrics.avg_total_return_pct)}%`" />
              <MetricCard label="验证超额" :value="`${metricValue(validationMetric(latestModel, 'avg_excess_return_pct') ?? latestModel.metrics.avg_excess_return_pct)}%`" />
              <MetricCard label="验证回撤" :value="`${metricValue(validationMetric(latestModel, 'avg_max_drawdown_pct') ?? latestModel.metrics.avg_max_drawdown_pct)}%`" />
            </div>
            <div v-if="validationBlockers(latestModel).length > 0" class="rounded-[14px] border border-amber-300/20 bg-amber-300/[0.08] p-3 text-xs text-amber-100">
              <div class="font-semibold">验证未完全通过</div>
              <div v-for="blocker in validationBlockers(latestModel)" :key="blocker" class="mt-1">{{ blocker }}</div>
            </div>
            <div v-if="topEvaluation(latestModel)" class="rounded-[14px] border border-white/8 bg-white/[0.03] p-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div class="font-semibold">回放收益样本</div>
                  <div class="mt-1 text-xs text-[var(--text-tertiary)]">{{ evaluationTitle(topEvaluation(latestModel)) }}</div>
                </div>
                <span class="status-chip subtle">{{ tradeDetails(topEvaluation(latestModel)).length }} 笔明细</span>
              </div>
              <div class="mt-3 grid grid-cols-3 gap-2 text-xs">
                <MetricCard label="策略收益" :value="`${metricValue(topEvaluation(latestModel)?.total_return_pct)}%`" />
                <MetricCard label="基准涨幅" :value="`${metricValue(topEvaluation(latestModel)?.benchmark_return_pct)}%`" />
                <MetricCard label="最大回撤" :value="`${metricValue(topEvaluation(latestModel)?.max_drawdown_pct)}%`" />
              </div>
              <div v-if="tradeDetails(topEvaluation(latestModel)).length > 0" class="mt-3 max-h-[260px] overflow-auto rounded-[12px] border border-white/8">
                <table class="data-table text-xs">
                  <thead>
                    <tr>
                      <th>日期</th>
                      <th>方向</th>
                      <th>数量</th>
                      <th>价格</th>
                      <th>单次收益</th>
                      <th>收益率</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="trade in tradeDetails(topEvaluation(latestModel)).slice(0, 20)" :key="`${trade.symbol}-${trade.sequence}`">
                      <td class="mono-data">{{ trade.trade_date }}</td>
                      <td><span :class="['status-chip', trade.side === 'buy' ? 'positive' : 'subtle']">{{ trade.side === 'buy' ? '买入' : '卖出' }}</span></td>
                      <td class="mono-data">{{ metricValue(trade.shares) }}</td>
                      <td class="mono-data">{{ metricValue(trade.price) }}</td>
                      <td class="mono-data">{{ moneyMetric(trade.realized_profit) }}</td>
                      <td class="mono-data">{{ nullablePercentMetric(trade.position_return_pct) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else class="mt-3 text-xs text-[var(--text-tertiary)]">当前样本没有实际买卖成交。</div>
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
              <th>算法</th>
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
              <td><span class="status-chip subtle">{{ algorithmLabel(model.algorithm) }}</span></td>
              <td>
                <div class="flex flex-col items-start gap-2">
                  <span class="status-chip subtle">{{ statusLabel(model.status) }}</span>
                  <button
                    class="primary-button !min-h-9 px-3 text-xs"
                    type="button"
                    :disabled="loading || model.status === 'active'"
                    @click="activateModel(model)"
                  >
                    {{ model.status === 'active' ? '已启用' : '启用模型' }}
                  </button>
                </div>
              </td>
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
import { fetchLatestRLTrainingJob, fetchRLModels, fetchRLTrainingJob, fetchRLTrainingScopes, resolveRLTrainingSymbols, submitRLTrainingJob, updateRLModelStatus } from '../api/market'
import type { RLModelArtifact, RLTrainingJob, RLTrainingScope, RLTrainingScopeOption, RLTrainingSymbol } from '../types/rlTraining'
import { formatDateTime as formatApiDateTime } from '../utils/format'
import { getApiErrorMessage, getApiStatus } from '../utils/http'
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

function isoDate(offsetDays = 0): string {
  const value = new Date()
  value.setDate(value.getDate() + offsetDays)
  return value.toISOString().slice(0, 10)
}

const form = reactive({
  modelName: 'RL PPO 日线模型',
  algorithm: 'ppo_trading' as 'ppo_trading',
  scopes: ['watchlist'] as RLTrainingScope[],
  manualSymbols: '',
  startDate: isoDate(-365),
  endDate: isoDate(),
  limit: 50,
  totalTimesteps: 100000,
  trainSplitPct: 0.8,
  ppoNSteps: 512,
  ppoBatchSize: 64,
  ppoLearningRate: 0.00031,
  initialCash: 100000,
  maxPositionPct: 0.6,
  rewardMode: 'risk_adjusted_excess_return' as 'net_worth_change' | 'excess_return' | 'drawdown_penalty' | 'risk_adjusted_excess_return',
  drawdownPenaltyCoef: 0.06,
  turnoverPenaltyCoef: 0.001,
  minValidationBars: 5,
})

const canTrain = computed(() => form.modelName.trim().length > 0 && form.scopes.length > 0)

onMounted(async () => {
  await Promise.all([loadScopes(), loadModels()])
  await restoreLatestJob()
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

function toggleScope(scope: RLTrainingScope): void {
  if (form.scopes.includes(scope)) {
    if (form.scopes.length === 1) {
      return
    }
    form.scopes = form.scopes.filter((item) => item !== scope)
  } else {
    form.scopes = [...form.scopes, scope]
  }
  resolvedSymbols.value = []
}

function primaryScope(): RLTrainingScope {
  return form.scopes[0] ?? 'watchlist'
}

function boundedNumber(value: unknown, fallback: number, min?: number, max?: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return fallback
  }
  return Math.min(max ?? parsed, Math.max(min ?? parsed, parsed))
}

async function loadScopes(): Promise<void> {
  const payload = await fetchRLTrainingScopes()
  scopeOptions.value = payload.scopes
}

async function loadModels(): Promise<void> {
  const payload = await fetchRLModels()
  models.value = payload.models
}

async function activateModel(model: RLModelArtifact): Promise<void> {
  loading.value = true
  error.value = ''
  successMessage.value = ''
  try {
    const updated = await updateRLModelStatus(model.model_id, 'active')
    successMessage.value = `模型已启用：${updated.name}`
    await loadModels()
    if (latestModel.value?.model_id === updated.model_id) {
      latestModel.value = updated
    }
  } catch (err: unknown) {
    error.value = getApiErrorMessage(err, '模型启用失败')
  } finally {
    loading.value = false
  }
}

async function restoreLatestJob(): Promise<void> {
  try {
    const job = await fetchLatestRLTrainingJob()
    if (!job) {
      return
    }
    currentJob.value = job
    if (job.status === 'queued' || job.status === 'running') {
      loading.value = true
      startPolling(job.job_id)
      return
    }
    applyCompletedJob(job)
  } catch (err: unknown) {
    error.value = getApiErrorMessage(err, '训练任务恢复失败')
  }
}

async function resolveSymbols(): Promise<void> {
  error.value = ''
  try {
    const payload = await resolveRLTrainingSymbols({
      scope: primaryScope(),
      scopes: form.scopes,
      symbols: manualSymbols(),
      limit: boundedNumber(form.limit, 50, 1, 300),
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
      algorithm: form.algorithm,
      scope: primaryScope(),
      scopes: form.scopes,
      symbols: manualSymbols(),
      start_date: form.startDate || null,
      end_date: form.endDate || null,
      limit: boundedNumber(form.limit, 50, 1, 300),
      total_timesteps: boundedNumber(form.totalTimesteps, 100000, 1000, 2000000),
      train_split_pct: boundedNumber(form.trainSplitPct, 0.8, 0.5, 0.95),
      ppo_n_steps: boundedNumber(form.ppoNSteps, 512, 64, 8192),
      ppo_batch_size: boundedNumber(form.ppoBatchSize, 64, 16, 2048),
      ppo_learning_rate: boundedNumber(form.ppoLearningRate, 0.00031, 0.00001, 0.01),
      initial_cash: boundedNumber(form.initialCash, 100000, 1),
      max_position_pct: boundedNumber(form.maxPositionPct, 0.6, 0, 1),
      reward_mode: form.rewardMode,
      drawdown_penalty_coef: boundedNumber(form.drawdownPenaltyCoef, 0.06, 0, 1),
      turnover_penalty_coef: boundedNumber(form.turnoverPenaltyCoef, 0.001, 0, 1),
      min_validation_bars: boundedNumber(form.minValidationBars, 5, 1, 252),
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
    if (job.status === 'succeeded' || job.status === 'failed') {
      stopPolling()
      loading.value = false
      applyCompletedJob(job)
      if (job.status === 'succeeded') {
        await loadModels()
      }
    }
  } catch (err: unknown) {
    if (getApiStatus(err) === 404) {
      const latest = await fetchLatestRLTrainingJob()
      if (latest) {
        currentJob.value = latest
        if (latest.status === 'queued' || latest.status === 'running') {
          startPolling(latest.job_id)
          return
        }
        stopPolling()
        loading.value = false
        applyCompletedJob(latest)
        return
      }
      stopPolling()
      loading.value = false
      currentJob.value = null
      error.value = '训练任务记录不存在，可能是后端重启或任务文件被清理；请重新提交训练。'
      return
    }
    stopPolling()
    loading.value = false
    error.value = getApiErrorMessage(err, '训练进度刷新失败')
  }
}

function applyCompletedJob(job: RLTrainingJob): void {
  if (job.status === 'succeeded') {
    if (job.model) {
      latestModel.value = job.model
      resolvedSymbols.value = job.model.symbols
      successMessage.value = `训练完成：${job.model.name}`
    } else {
      successMessage.value = '训练完成'
    }
  } else if (job.status === 'failed') {
    error.value = failedJobMessage(job)
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

function percentMetric(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return `${(value * 100).toFixed(1)}%`
  }
  return '--'
}

function nullablePercentMetric(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return `${value.toFixed(2)}%`
  }
  return '--'
}

function moneyMetric(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value.toFixed(2)
  }
  return '--'
}

function topEvaluation(model: RLModelArtifact | null): Record<string, unknown> | null {
  const evaluations = model?.evaluations ?? []
  if (evaluations.length === 0) {
    return null
  }
  return [...evaluations].sort((left, right) => Number(right.total_return_pct ?? 0) - Number(left.total_return_pct ?? 0))[0]
}

function validationMetric(model: RLModelArtifact | null, key: string): unknown {
  const splitMetrics = model?.metrics?.splits
  if (typeof splitMetrics !== 'object' || splitMetrics === null || !('validation' in splitMetrics)) {
    return undefined
  }
  const validation = (splitMetrics as Record<string, unknown>).validation
  if (typeof validation !== 'object' || validation === null) {
    return undefined
  }
  return (validation as Record<string, unknown>)[key]
}

function evaluationTitle(evaluation: Record<string, unknown> | null): string {
  if (!evaluation) {
    return ''
  }
  return `${evaluation.symbol ?? '--'} · 记录 ${metricValue(evaluation.records)} 条 · 交易 ${metricValue(evaluation.trade_count)} 次`
}

function tradeDetails(evaluation: Record<string, unknown> | null): Array<Record<string, unknown>> {
  const details = evaluation?.trade_details_sample ?? evaluation?.trade_details
  return Array.isArray(details) ? details.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null) : []
}

function algorithmLabel(algorithm: string): string {
  const mapping: Record<string, string> = {
    ppo_trading: 'PPO',
  }
  return mapping[algorithm] ?? algorithm
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

function progressDetails(job: RLTrainingJob): string[] {
  return Array.isArray(job.progress_details) ? job.progress_details.filter(Boolean).map(normalizeTrainingError).slice(0, 10) : []
}

function failedJobMessage(job: RLTrainingJob): string {
  const details = progressDetails(job)
  const primary = normalizeTrainingError(job.error || details[0] || 'RL 模型训练失败')
  const extra = details.filter((detail) => detail && detail !== primary)
  return extra.length ? [primary, ...extra].join('\n') : primary
}

function normalizeTrainingError(message: string): string {
  if (message === 'PPO training requires at least one symbol with two daily bars') {
    return '训练/验证切分后没有足够日线；请扩大训练日期范围或降低最小验证 Bar。'
  }
  return message
}

function currentSyncSymbol(job: RLTrainingJob): string | null {
  const label = job.progress_label || ''
  const match = label.match(/(?:正在获取|已保存|跳过|获取)\s+([a-z]{2}\d{6})\s+日线/)
  return match?.[1] ?? null
}

function validationPassed(model: RLModelArtifact): boolean {
  return Boolean((model.validation as { passed?: unknown } | undefined)?.passed)
}

function validationBlockers(model: RLModelArtifact): string[] {
  const blockers = (model.validation as { blockers?: unknown } | undefined)?.blockers
  return Array.isArray(blockers) ? blockers.filter((item): item is string => typeof item === 'string') : []
}
</script>
