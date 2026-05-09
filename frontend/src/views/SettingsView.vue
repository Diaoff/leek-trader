<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="偏好设置"
        subtitle="集中配置模拟交易费用、智能选股参数和策略自动执行频率。"
      />
      <div class="token-row">
        <button class="secondary-button" type="button" :disabled="store.loading || store.saving" @click="loadPreferences">
          刷新设置
        </button>
        <button class="secondary-button" type="button" :disabled="store.saving" @click="resetDefaults">
          重置默认
        </button>
        <button class="primary-button" type="button" :disabled="store.saving || !ready" @click="savePreferences">
          {{ store.saving ? '保存中...' : '保存偏好' }}
        </button>
      </div>
    </div>

    <ErrorAlert :message="store.error" type="error" />
    <SuccessAlert :message="successMessage" />

    <div v-if="store.loading" class="panel compact-empty">正在加载偏好设置...</div>

    <div v-else class="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <div class="panel space-y-5">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">Trading Cost</div>
            <h3 class="panel-title mt-3">交易费用</h3>
            <p class="panel-subtitle">费用会真实影响模拟成交后的现金、成交费和盈亏。</p>
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-3">
          <label class="space-y-2">
            <span class="field-label">佣金费率</span>
            <input v-model.number="form.trading.commission_rate" class="field-input mono-data" type="number" min="0" max="0.1" step="0.0001" />
            <span class="field-help">当前 {{ formatRate(form.trading.commission_rate) }}</span>
          </label>
          <label class="space-y-2">
            <span class="field-label">最低佣金</span>
            <input v-model.number="form.trading.min_commission" class="field-input mono-data" type="number" min="0" step="0.01" />
            <span class="field-help">每笔佣金低于该值时按最低值收取。</span>
          </label>
          <label class="space-y-2">
            <span class="field-label">卖出印花税</span>
            <input v-model.number="form.trading.stamp_tax_rate" class="field-input mono-data" type="number" min="0" max="0.1" step="0.0001" />
            <span class="field-help">当前 {{ formatRate(form.trading.stamp_tax_rate) }}，仅卖出收取。</span>
          </label>
        </div>

        <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4 text-sm text-[var(--text-secondary)]">
          <div>买入示例：10,000 元成交额约扣 {{ formatCurrency(exampleBuyFee) }} 费用。</div>
          <div class="mt-2">卖出示例：10,000 元成交额约扣 {{ formatCurrency(exampleSellFee) }} 费用。</div>
        </div>
      </div>

      <div class="panel space-y-5">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">Strategy Scheduler</div>
            <h3 class="panel-title mt-3">策略执行频率</h3>
            <p class="panel-subtitle">后台仍每分钟检查一次，到达设置间隔才运行活跃策略。</p>
          </div>
        </div>

        <label class="flex items-center justify-between gap-4 rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
          <span>
            <span class="font-semibold">启用自动策略轮询</span>
            <span class="mt-1 block text-sm text-[var(--text-secondary)]">关闭后仍可手动运行策略。</span>
          </span>
          <input v-model="form.strategy_scheduler.enabled" class="h-5 w-5 accent-[var(--accent)]" type="checkbox" />
        </label>

        <label class="space-y-2">
          <span class="field-label">执行间隔（秒）</span>
          <input v-model.number="form.strategy_scheduler.interval_seconds" class="field-input mono-data" type="number" min="60" max="86400" step="60" />
          <span class="field-help">建议不少于 300 秒，避免过于频繁地产生策略运行记录。</span>
        </label>

        <label class="flex items-center justify-between gap-4 rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
          <span>
            <span class="font-semibold">仅交易时段执行</span>
            <span class="mt-1 block text-sm text-[var(--text-secondary)]">关闭后后台任务会忽略交易时间过滤。</span>
          </span>
          <input v-model="form.strategy_scheduler.trading_hours_only" class="h-5 w-5 accent-[var(--accent)]" type="checkbox" />
        </label>
      </div>

      <div class="panel space-y-5 xl:col-span-2">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">Smart Selection</div>
            <h3 class="panel-title mt-3">智能选股</h3>
            <p class="panel-subtitle">调整日报开关、推荐数量、分数阈值和风控参数。</p>
          </div>
          <span class="status-chip subtle">固定时间 {{ form.smart_selection.schedule_time || '20:00' }}</span>
        </div>

        <label class="flex items-center justify-between gap-4 rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
          <span>
            <span class="font-semibold">启用智能选股定时任务</span>
            <span class="mt-1 block text-sm text-[var(--text-secondary)]">关闭后不会自动生成日报，但仍可手动执行。</span>
          </span>
          <input v-model="form.smart_selection.enabled" class="h-5 w-5 accent-[var(--accent)]" type="checkbox" />
        </label>

        <div class="grid gap-4 md:grid-cols-4">
          <label class="space-y-2">
            <span class="field-label">最低评分</span>
            <input v-model.number="smartConfig.min_score" class="field-input mono-data" type="number" min="0" max="100" step="1" />
          </label>
          <label class="space-y-2">
            <span class="field-label">最多推荐</span>
            <input v-model.number="smartConfig.max_recommendations" class="field-input mono-data" type="number" min="1" max="50" step="1" />
          </label>
          <label class="space-y-2">
            <span class="field-label">候选批量</span>
            <input v-model.number="smartConfig.batch_size" class="field-input mono-data" type="number" min="1" max="500" step="1" />
          </label>
          <label class="space-y-2">
            <span class="field-label">止损比例</span>
            <input v-model.number="smartConfig.stop_loss_pct" class="field-input mono-data" type="number" min="0" max="50" step="0.1" />
          </label>
          <label class="space-y-2">
            <span class="field-label">目标收益</span>
            <input v-model.number="smartConfig.target_gain_pct" class="field-input mono-data" type="number" min="0" max="200" step="0.1" />
          </label>
          <label class="space-y-2">
            <span class="field-label">单票最大仓位</span>
            <input v-model.number="smartConfig.max_position_pct" class="field-input mono-data" type="number" min="0" max="100" step="0.1" />
          </label>
          <label class="space-y-2">
            <span class="field-label">最低盈亏比</span>
            <input v-model.number="smartConfig.min_risk_reward" class="field-input mono-data" type="number" min="0" max="10" step="0.1" />
          </label>
          <label class="space-y-2">
            <span class="field-label">最低成交额</span>
            <input v-model.number="smartConfig.min_volume" class="field-input mono-data" type="number" min="0" step="0.1" />
          </label>
          <label class="space-y-2">
            <span class="field-label">当日券商样本阈值</span>
            <input v-model.number="smartConfig.min_latest_date_rows" class="field-input mono-data" type="number" min="1" max="1000" step="1" />
            <span class="field-help">当天推荐少于该数量时，继续翻页并补全前一日推荐。</span>
          </label>
        </div>
      </div>

      <div class="panel space-y-5 border border-red-300/20 bg-red-300/[0.04] xl:col-span-2">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label text-red-200">Account Reset</div>
            <h3 class="panel-title mt-3">重置我的账户</h3>
            <p class="panel-subtitle">清空当前登录用户的模拟交易流水、持仓、委托、成交和权益快照，并把本账户资金重置为新的起点。</p>
          </div>
          <span class="status-chip subtle">仅当前账户</span>
        </div>

        <div class="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(220px,0.4fr)]">
          <label class="space-y-2">
            <span class="field-label">确认文本</span>
            <input v-model="resetForm.confirmation" class="field-input mono-data" type="text" placeholder="输入 RESET 才能执行" />
            <span class="field-help">仅会重置当前登录用户的默认模拟账户，不影响其他用户账户。</span>
          </label>
          <label class="space-y-2">
            <span class="field-label">初始资金</span>
            <input v-model.number="resetForm.initialCash" class="field-input mono-data" type="number" min="0" step="1000" />
            <span class="field-help">当前默认 {{ formatCurrency(resetForm.initialCash || 0) }}，可修改后作为新的账户起点。</span>
          </label>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <button class="secondary-button border-red-300/30 text-red-100" type="button" :disabled="resetting || resetForm.confirmation !== 'RESET'" @click="resetTradingStateNow">
            {{ resetting ? '重置中...' : '重置我的账户' }}
          </button>
          <span v-if="lastResetSummary" class="text-sm text-[var(--text-secondary)]">{{ lastResetSummary }}</span>
        </div>
      </div>
    </div>

  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import ErrorAlert from '../components/ErrorAlert.vue'
import PageHeader from '../components/PageHeader.vue'
import SuccessAlert from '../components/SuccessAlert.vue'
import { fetchAccounts } from '../api/accounts'
import { resetTradingState } from '../api/devtools'
import { usePreferencesStore } from '../stores/preferences'
import type { Preferences } from '../types/preferences'
import { formatCurrency } from '../utils/format'

const store = usePreferencesStore()
const successMessage = ref('')
const resetting = ref(false)
const lastResetSummary = ref('')
const form = reactive<Preferences>({
  tenant_id: 'local',
  trading: {
    commission_rate: 0.0003,
    min_commission: 5,
    stamp_tax_rate: 0.0005,
    stamp_tax_side: 'sell',
  },
  smart_selection: {
    enabled: true,
    schedule_time: '20:00',
    config_payload: {},
  },
  strategy_scheduler: {
    enabled: true,
    interval_seconds: 300,
    trading_hours_only: true,
  },
  updated_at: '',
})

const smartConfig = reactive({
  min_score: 30,
  max_recommendations: 10,
  batch_size: 50,
  min_volume: 1,
  stop_loss_pct: 5,
  target_gain_pct: 15,
  max_position_pct: 18,
  min_risk_reward: 1,
  min_latest_date_rows: 50,
})

const resetForm = reactive({
  confirmation: '',
  initialCash: 1000000,
})

const ready = computed(() => !store.loading)
const exampleBuyFee = computed(() => calculateFee(10000, false))
const exampleSellFee = computed(() => calculateFee(10000, true))

function applyPreferences(preferences: Preferences): void {
  Object.assign(form, JSON.parse(JSON.stringify(preferences)))
  const payload = form.smart_selection.config_payload as Record<string, unknown>
  const candidatePool = (payload.candidate_pool ?? {}) as Record<string, unknown>
  const institutionPool = (payload.institution_rating_pool ?? {}) as Record<string, unknown>
  const riskControl = (payload.risk_control ?? {}) as Record<string, unknown>
  smartConfig.min_score = numberValue(payload.min_score, 30)
  smartConfig.max_recommendations = numberValue(payload.max_recommendations, 10)
  smartConfig.min_volume = numberValue(payload.min_volume, 1)
  smartConfig.batch_size = numberValue(candidatePool.batch_size, 50)
  smartConfig.min_latest_date_rows = numberValue(institutionPool.min_latest_date_rows ?? institutionPool.min_current_day_rows, 50)
  smartConfig.stop_loss_pct = numberValue(riskControl.stop_loss_pct, 5)
  smartConfig.target_gain_pct = numberValue(riskControl.target_gain_pct, 15)
  smartConfig.max_position_pct = numberValue(riskControl.max_position_pct, 18)
  smartConfig.min_risk_reward = numberValue(riskControl.min_risk_reward, 1)
}

function buildSmartConfig(): Record<string, unknown> {
  const payload = { ...(form.smart_selection.config_payload as Record<string, unknown>) }
  payload.min_score = smartConfig.min_score
  payload.max_recommendations = smartConfig.max_recommendations
  payload.min_volume = smartConfig.min_volume
  payload.candidate_pool = {
    ...((payload.candidate_pool ?? {}) as Record<string, unknown>),
    batch_size: smartConfig.batch_size,
  }
  payload.institution_rating_pool = {
    ...((payload.institution_rating_pool ?? {}) as Record<string, unknown>),
    min_latest_date_rows: smartConfig.min_latest_date_rows,
  }
  payload.risk_control = {
    ...((payload.risk_control ?? {}) as Record<string, unknown>),
    stop_loss_pct: smartConfig.stop_loss_pct,
    target_gain_pct: smartConfig.target_gain_pct,
    max_position_pct: smartConfig.max_position_pct,
    min_risk_reward: smartConfig.min_risk_reward,
  }
  return payload
}

async function loadPreferences(): Promise<void> {
  successMessage.value = ''
  await Promise.all([store.fetchPreferences(), loadDefaultAccount()])
  if (store.preferences) {
    applyPreferences(store.preferences)
  }
}

async function loadDefaultAccount(): Promise<void> {
  const accounts = await fetchAccounts()
  const account = accounts[0]
  if (account) {
    resetForm.initialCash = numberValue(account.initial_cash, resetForm.initialCash)
  }
}

async function savePreferences(): Promise<void> {
  successMessage.value = ''
  const saved = await store.updatePreferences({
    trading: {
      commission_rate: form.trading.commission_rate,
      min_commission: form.trading.min_commission,
      stamp_tax_rate: form.trading.stamp_tax_rate,
    },
    smart_selection: {
      enabled: form.smart_selection.enabled,
      config_payload: buildSmartConfig(),
    },
    strategy_scheduler: {
      enabled: form.strategy_scheduler.enabled,
      interval_seconds: form.strategy_scheduler.interval_seconds,
      trading_hours_only: form.strategy_scheduler.trading_hours_only,
    },
  })
  applyPreferences(saved)
  successMessage.value = '偏好设置已保存'
}

function resetDefaults(): void {
  form.trading.commission_rate = 0.0003
  form.trading.min_commission = 5
  form.trading.stamp_tax_rate = 0.0005
  form.strategy_scheduler.enabled = true
  form.strategy_scheduler.interval_seconds = 300
  form.strategy_scheduler.trading_hours_only = true
  smartConfig.min_score = 30
  smartConfig.max_recommendations = 10
  smartConfig.batch_size = 50
  smartConfig.min_volume = 1
  smartConfig.stop_loss_pct = 5
  smartConfig.target_gain_pct = 15
  smartConfig.max_position_pct = 18
  smartConfig.min_risk_reward = 1
  smartConfig.min_latest_date_rows = 50
  successMessage.value = '已恢复默认值，点击保存后生效'
}

async function resetTradingStateNow(): Promise<void> {
  resetting.value = true
  successMessage.value = ''
  lastResetSummary.value = ''
  try {
    const result = await resetTradingState({
      confirmation: resetForm.confirmation,
      initial_cash: Number.isFinite(resetForm.initialCash) ? resetForm.initialCash : null,
    })
    const deletedTotal = Object.values(result.deleted_counts).reduce((sum, count) => sum + count, 0)
    lastResetSummary.value = `已删除 ${deletedTotal} 条记录，账户资金重置为 ${formatCurrency(Number(result.total_equity))}`
    successMessage.value = '当前账户已重置，可以重新开始统计盈亏'
    resetForm.initialCash = Number(result.initial_cash)
    resetForm.confirmation = ''
  } finally {
    resetting.value = false
  }
}

function numberValue(value: unknown, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function calculateFee(tradeValue: number, sell: boolean): number {
  const commissionBase = tradeValue * Math.max(0, form.trading.commission_rate)
  const commission = commissionBase > 0 ? Math.max(commissionBase, Math.max(0, form.trading.min_commission)) : 0
  const stampTax = sell ? tradeValue * Math.max(0, form.trading.stamp_tax_rate) : 0
  return commission + stampTax
}

function formatRate(value: number): string {
  return `${(Number(value || 0) * 100).toFixed(3)}%`
}

onMounted(() => {
  void loadPreferences()
})
</script>
