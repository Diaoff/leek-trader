<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="智能选股"
        subtitle="独立展示规则型选股日报、任务状态、推荐明细和基础偏好配置。"
      />
      <div class="token-row">
        <span class="status-chip subtle">最近同步 {{ store.lastUpdated }}</span>
        <button class="secondary-button" type="button" :disabled="store.loading" @click="reload">
          刷新
        </button>
        <button class="primary-button" type="button" :disabled="store.running" @click="runSelection">
          {{ store.running ? '提交中...' : '手动执行' }}
        </button>
      </div>
    </div>

    <ErrorAlert :message="store.error" type="warning" />

    <div class="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_340px]">
      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">Selection Status</div>
            <h3 class="panel-title mt-3">运行概览</h3>
            <p class="panel-subtitle">成功日报与最近任务分开显示，失败不会覆盖上一份可读报告。</p>
          </div>
          <span :class="['status-chip', taskTone(currentStatus)]">{{ taskLabel(currentStatus) }}</span>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">最近日报</div>
            <div class="mt-2 text-lg font-semibold">{{ snapshotTimeLabel }}</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ store.snapshot?.summary || '暂无日报摘要' }}</div>
          </div>
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">最近任务</div>
            <div class="mt-2 text-lg font-semibold">{{ taskLabel(currentStatus) }}</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ taskFeedback }}</div>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-3">
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">推荐数量</div>
            <div class="mt-2 text-2xl font-semibold">{{ activeRun?.recommendation_count ?? 0 }}</div>
          </div>
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">候选池</div>
            <div class="mt-2 text-2xl font-semibold">{{ activeRun?.candidate_pool_size ?? 0 }}</div>
          </div>
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">调度时间</div>
            <div class="mt-2 text-2xl font-semibold">{{ store.config?.schedule_time ?? '20:00' }}</div>
          </div>
        </div>

        <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="muted-text text-xs">报告正文</div>
            <div class="token-row">
              <span v-if="copyStatusText" :class="['status-chip', copyState === 'success' ? 'positive' : 'negative']">
                {{ copyStatusText }}
              </span>
              <button class="secondary-button" type="button" :disabled="!reportBody" @click="copyReport">
                复制 Markdown
              </button>
            </div>
          </div>
          <div
            v-if="reportBody"
            class="report-output markdown-body mt-3 text-sm leading-7 text-[var(--text-secondary)]"
            v-html="renderedReportBody"
          />
          <div v-else class="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
            暂无可展示报告，手动执行后会在这里展示最近成功日报。
          </div>
        </div>
      </div>

      <div class="space-y-4">
        <div class="panel">
          <div class="panel-header !mb-0">
            <div>
              <div class="section-label">Preference</div>
              <h3 class="panel-title mt-3">基础偏好</h3>
              <p class="panel-subtitle">V1 仅暴露启停状态，默认每日 20:00 执行。</p>
            </div>
          </div>

          <label class="mt-4 flex items-center justify-between gap-4 rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div>
              <div class="font-semibold">启用定时执行</div>
              <div class="mt-1 text-sm text-[var(--text-secondary)]">
                关闭后不会在每日 20:00 自动生成日报，但仍可手动执行。
              </div>
            </div>
            <input
              class="h-5 w-5 accent-[var(--accent)]"
              type="checkbox"
              :checked="store.config?.enabled ?? true"
              :disabled="store.saving"
              @change="toggleEnabled"
            />
          </label>

          <div class="mt-4 rounded-[18px] border border-white/5 bg-white/[0.03] p-4 text-sm text-[var(--text-secondary)]">
            <div>固定执行时间：{{ store.config?.schedule_time ?? '20:00' }}（Asia/Shanghai）</div>
            <div class="mt-2">候选池模式：{{ candidatePoolMode }}</div>
            <div class="mt-2">最多推荐：{{ maxRecommendations }}</div>
            <div class="mt-2">风险控制：目标 {{ targetGainLabel }} / 止损 {{ stopLossLabel }}</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header !mb-0">
            <div>
              <div class="section-label">Task History</div>
              <h3 class="panel-title mt-3">最近任务历史</h3>
              <p class="panel-subtitle">展示最新任务状态与摘要，便于确认是否成功落库。</p>
            </div>
          </div>

          <div v-if="store.history.length === 0" class="compact-empty">暂无任务历史</div>
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="run in store.history.slice(0, 6)"
              :key="run.id"
              class="rounded-[16px] border border-white/5 bg-black/10 p-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="font-semibold">#{{ run.id }}</div>
                <span :class="['status-chip', taskTone(run.status)]">{{ taskLabel(run.status) }}</span>
              </div>
              <div class="mt-2 text-sm text-[var(--text-secondary)]">
                {{ run.generated_at ? formatDateTime(run.generated_at) : formatDateTime(run.started_at) }}
              </div>
              <div class="mt-1 text-xs text-[var(--text-tertiary)]">
                {{ run.error_message || run.summary || '无摘要' }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <div class="section-label">Selection List</div>
          <h3 class="panel-title mt-3">推荐明细</h3>
          <p class="panel-subtitle">按最近一份成功日报展示评分、目标价、止损价和维度拆解。</p>
        </div>
      </div>

      <div v-if="store.items.length === 0" class="compact-empty">暂无推荐明细</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[980px] text-left text-sm">
          <thead class="border-b border-white/10 text-[var(--text-tertiary)]">
            <tr>
              <th class="py-3 pr-4 font-medium">标的</th>
              <th class="py-3 pr-4 font-medium">综合评分</th>
              <th class="py-3 pr-4 font-medium">现价 / 涨跌</th>
              <th class="py-3 pr-4 font-medium">目标价</th>
              <th class="py-3 pr-4 font-medium">止损价</th>
              <th class="py-3 pr-4 font-medium">维度拆解</th>
              <th class="py-3 pr-4 font-medium">标签</th>
              <th class="py-3 font-medium">AI</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in store.items"
              :key="item.symbol"
              class="border-b border-white/5 align-top last:border-0"
            >
              <td class="py-4 pr-4">
                <div class="font-semibold">{{ item.name }}</div>
                <div class="mono-data muted-text mt-1">{{ item.code }}</div>
                <div class="mt-2 text-xs text-[var(--text-tertiary)]">{{ item.reason }}</div>
              </td>
              <td class="py-4 pr-4">{{ item.score.toFixed(1) }}</td>
              <td class="py-4 pr-4">
                <div>{{ formatNullableCurrency(item.price) }}</div>
                <div :class="['mt-1 text-xs', toneClass(item.change_pct)]">{{ formatSignedPercent(item.change_pct) }}</div>
              </td>
              <td class="py-4 pr-4">{{ formatNullableCurrency(item.target_price) }}</td>
              <td class="py-4 pr-4">{{ formatNullableCurrency(item.stop_loss_price) }}</td>
              <td class="py-4 pr-4">
                <div class="text-xs text-[var(--text-secondary)]">
                  趋势 {{ scoreValue(item.dimension_scores.trend) }} /20
                </div>
                <div class="mt-1 text-xs text-[var(--text-secondary)]">
                  资金 {{ scoreValue(item.dimension_scores.fund_flow) }} /25
                </div>
                <div class="mt-1 text-xs text-[var(--text-secondary)]">
                  形态 {{ scoreValue(item.dimension_scores.k_pattern) }} /25
                </div>
                <div class="mt-1 text-xs text-[var(--text-secondary)]">
                  九转 {{ scoreValue(item.dimension_scores.nine_turn) }} /15
                </div>
              </td>
              <td class="py-4 pr-4">
                <div class="flex flex-wrap gap-2">
                  <span
                    v-for="tag in item.tags"
                    :key="tag"
                    class="rounded-full border border-white/10 px-2 py-1 text-xs text-[var(--text-secondary)]"
                  >
                    {{ tag }}
                  </span>
                </div>
              </td>
              <td class="py-4">
                <RouterLink class="text-[var(--accent)] transition hover:opacity-80" :to="{ name: 'ai', query: { symbol: item.symbol } }">
                  查看
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import ErrorAlert from '../components/ErrorAlert.vue'
import PageHeader from '../components/PageHeader.vue'
import { useSmartSelectionStore } from '../stores/smartSelection'
import { formatCurrency, formatDateTime } from '../utils/format'
import { renderMarkdown } from '../utils/markdown'

const store = useSmartSelectionStore()
const copyState = ref<'idle' | 'success' | 'error'>('idle')
let copyTimer: ReturnType<typeof setTimeout> | null = null

const activeRun = computed(() => store.latestTask ?? store.snapshot)
const currentStatus = computed(() => store.latestTask?.status ?? store.snapshot?.status ?? 'queued')
const snapshotTimeLabel = computed(() => (store.snapshot?.generated_at ? formatDateTime(store.snapshot.generated_at) : '暂无日报'))
const taskFeedback = computed(() => store.latestTask?.error_message || store.triggerMessage || '无额外任务反馈')
const candidatePoolMode = computed(() => String((store.config?.config_payload.candidate_pool as Record<string, unknown> | undefined)?.mode ?? 'hybrid'))
const maxRecommendations = computed(() => Number(store.config?.config_payload.max_recommendations ?? 10))
const stopLossLabel = computed(() => `${Number((store.config?.config_payload.risk_control as Record<string, unknown> | undefined)?.stop_loss_pct ?? 5)}%`)
const targetGainLabel = computed(() => `${Number((store.config?.config_payload.risk_control as Record<string, unknown> | undefined)?.target_gain_pct ?? 15)}%`)
const reportBody = computed(() => store.snapshot?.report_body?.trim() ?? '')
const renderedReportBody = computed(() => (reportBody.value ? renderMarkdown(reportBody.value) : ''))
const copyStatusText = computed(() => {
  if (copyState.value === 'success') {
    return 'Markdown 已复制'
  }
  if (copyState.value === 'error') {
    return '复制失败'
  }
  return ''
})

function toneClass(value: number | null): string {
  if (value === null) {
    return 'muted-text'
  }
  if (value > 0) {
    return 'value-rise'
  }
  if (value < 0) {
    return 'value-fall'
  }
  return 'muted-text'
}

function formatNullableCurrency(value: number | null): string {
  return value === null ? '—' : formatCurrency(value)
}

function formatSignedPercent(value: number | null): string {
  if (value === null) {
    return '—'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function scoreValue(value: number | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—'
  }
  return value.toFixed(1)
}

function resetCopyState(delay = 1800): void {
  if (copyTimer) {
    clearTimeout(copyTimer)
  }
  copyTimer = setTimeout(() => {
    copyState.value = 'idle'
    copyTimer = null
  }, delay)
}

function copyWithFallback(value: string): void {
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', 'true')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

async function copyReport(): Promise<void> {
  if (!reportBody.value) {
    return
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(reportBody.value)
    } else {
      copyWithFallback(reportBody.value)
    }
    copyState.value = 'success'
  } catch {
    try {
      copyWithFallback(reportBody.value)
      copyState.value = 'success'
    } catch {
      copyState.value = 'error'
    }
  }
  resetCopyState()
}

function taskLabel(status: string): string {
  const mapping: Record<string, string> = {
    queued: '排队中',
    running: '运行中',
    succeeded: '成功',
    failed: '失败',
  }
  return mapping[status] ?? status
}

function taskTone(status: string): 'neutral' | 'positive' | 'negative' {
  if (status === 'succeeded') {
    return 'positive'
  }
  if (status === 'failed') {
    return 'negative'
  }
  return 'neutral'
}

async function reload(): Promise<void> {
  await store.loadPage()
}

async function runSelection(): Promise<void> {
  await store.triggerRun()
}

async function toggleEnabled(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  try {
    await store.saveEnabled(target.checked)
  } catch {
    target.checked = !target.checked
  }
}

onMounted(() => {
  void reload()
})

onBeforeUnmount(() => {
  if (copyTimer) {
    clearTimeout(copyTimer)
  }
  store.clearPoll()
})
</script>

<style scoped>
.report-output {
  overflow-x: auto;
}

.markdown-body {
  line-height: 1.8;
  word-break: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 0 0 12px;
  line-height: 1.3;
  letter-spacing: -0.03em;
}

.markdown-body :deep(h1) {
  font-size: 28px;
}

.markdown-body :deep(h2) {
  font-size: 22px;
}

.markdown-body :deep(h3) {
  font-size: 18px;
}

.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol),
.markdown-body :deep(blockquote),
.markdown-body :deep(pre),
.markdown-body :deep(table) {
  margin: 0 0 14px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
}

.markdown-body :deep(li + li) {
  margin-top: 6px;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid rgba(103, 183, 255, 0.38);
  margin-left: 0;
  padding-left: 14px;
  color: var(--text-secondary);
}

.markdown-body :deep(pre) {
  overflow: auto;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  background: rgba(2, 7, 14, 0.9);
  padding: 14px 16px;
}

.markdown-body :deep(code) {
  font-family: 'IBM Plex Mono', 'SFMono-Regular', ui-monospace, monospace;
  font-size: 12px;
}

.markdown-body :deep(:not(pre) > code) {
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 6px;
  color: #d6ebff;
}

.markdown-body :deep(a) {
  color: #8cc8ff;
  text-decoration: underline;
  text-decoration-color: rgba(140, 200, 255, 0.4);
}

.markdown-body :deep(table) {
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 10px 12px;
  text-align: left;
  vertical-align: top;
}

.markdown-body :deep(th) {
  color: var(--text-primary);
  font-weight: 600;
}

.markdown-body :deep(tbody tr:last-child td) {
  border-bottom: 0;
}
</style>
