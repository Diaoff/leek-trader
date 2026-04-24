<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="研究报告"
        subtitle="按最近一次成功快照展示结构化规则研究结果，并附带最近任务历史。"
      />
      <div class="token-row">
        <span class="status-chip subtle">最近同步 {{ store.lastUpdated }}</span>
        <button class="secondary-button" type="button" :disabled="store.reportLoading" @click="reload">
          刷新报告
        </button>
        <button class="primary-button" type="button" :disabled="store.running" @click="runResearch">
          {{ store.running ? '提交中...' : '手动生成快照' }}
        </button>
        <RouterLink class="ghost-button" :to="{ name: 'market' }">返回市场页</RouterLink>
      </div>
    </div>

    <ErrorAlert :message="store.error" type="warning" />

    <div class="grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)]">
      <div class="panel space-y-4">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">Snapshot Status</div>
            <h3 class="panel-title mt-3">研究快照状态</h3>
            <p class="panel-subtitle">成功快照用于展示结果，最新任务用于反馈排队、运行或失败状态。</p>
          </div>
          <span :class="['status-chip', taskTone(latestStatus)]">{{ taskLabel(latestStatus) }}</span>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">最近快照</div>
            <div class="mt-2 text-lg font-semibold">{{ snapshotTimeLabel }}</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ store.snapshot?.summary || '暂无研究结论' }}</div>
          </div>
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">最新任务</div>
            <div class="mt-2 text-lg font-semibold">{{ taskLabel(latestStatus) }}</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ taskFeedback }}</div>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">推荐数量</div>
            <div class="mt-2 text-2xl font-semibold">{{ activeRun?.recommendation_count ?? 0 }}</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">展示最近成功快照前 10 条。</div>
          </div>
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">候选池</div>
            <div class="mt-2 text-2xl font-semibold">{{ activeRun?.candidate_pool_size ?? 0 }}</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">用于规则引擎评分与板块聚合。</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">Task State</div>
            <h3 class="panel-title mt-3">任务反馈</h3>
            <p class="panel-subtitle">最新任务不会覆盖上一期成功快照，失败时仍保留可展示结果。</p>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">任务编号</div>
            <div class="mt-2 text-lg font-semibold">#{{ store.latestTask?.id ?? store.snapshot?.id ?? '—' }}</div>
          </div>
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">启动时间</div>
            <div class="mt-2 text-lg font-semibold">
              {{ latestStartedAt ? formatDateTime(latestStartedAt) : '暂无记录' }}
            </div>
          </div>
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">完成时间</div>
            <div class="mt-2 text-lg font-semibold">
              {{ latestFinishedAt ? formatDateTime(latestFinishedAt) : '尚未完成' }}
            </div>
          </div>
          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="muted-text text-xs">附加说明</div>
            <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ triggerMessage }}</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!store.snapshot && !store.reportLoading" class="panel empty-state !min-h-[320px]">
      <div>暂无研究快照</div>
      <div class="text-sm text-[var(--text-tertiary)]">点击上方“手动生成快照”后，成功结果会在这里展示。</div>
    </div>

    <template v-else>
      <div class="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
        <div class="panel space-y-4">
          <div class="panel-header !mb-0">
            <div>
              <div class="section-label">Daily Verdict</div>
              <h3 class="panel-title mt-3">今日结论</h3>
              <p class="panel-subtitle">{{ store.snapshot?.summary ?? '暂无摘要' }}</p>
            </div>
            <span class="status-chip subtle">
              {{ store.snapshot?.generated_at ? formatDateTime(store.snapshot.generated_at) : '未生成' }}
            </span>
          </div>

          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5 text-sm text-[var(--text-secondary)]">
            {{ store.snapshot?.report_summary ?? '暂无报告摘要' }}
          </div>

          <div class="grid gap-3 md:grid-cols-4">
            <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
              <div class="muted-text text-xs">候选池</div>
              <div class="mt-2 text-2xl font-semibold">{{ store.snapshot?.candidate_pool_size ?? 0 }}</div>
            </div>
            <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
              <div class="muted-text text-xs">推荐数</div>
              <div class="mt-2 text-2xl font-semibold">{{ store.snapshot?.recommendation_count ?? 0 }}</div>
            </div>
            <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
              <div class="muted-text text-xs">情绪分数</div>
              <div class="mt-2 text-2xl font-semibold">{{ store.snapshot?.market_sentiment?.score.toFixed(1) ?? '—' }}</div>
            </div>
            <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
              <div class="muted-text text-xs">北向资金</div>
              <div class="mt-2 text-lg font-semibold">{{ formatNetInflow(store.snapshot?.northbound_net_inflow ?? null) }}</div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="section-label">Momentum Board</div>
              <h3 class="panel-title mt-3">板块热度前排</h3>
              <p class="panel-subtitle">按候选池聚合后的领先板块。</p>
            </div>
          </div>
          <div v-if="(store.snapshot?.sector_momentum_top.length ?? 0) === 0" class="compact-empty">暂无板块热度</div>
          <div v-else class="space-y-3">
            <div
              v-for="item in store.snapshot?.sector_momentum_top"
              :key="item.sector"
              class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <div class="font-semibold">{{ item.rank }}. {{ item.sector }}</div>
                  <div class="mt-1 text-xs text-[var(--text-tertiary)]">
                    正收益占比 {{ (item.positive_ratio * 100).toFixed(0) }}%
                  </div>
                </div>
                <span :class="['status-chip', item.avg_change_pct >= 0 ? 'rise' : 'fall']">
                  {{ formatSignedPercent(item.avg_change_pct) }}
                </span>
              </div>
              <div class="mt-3 text-sm text-[var(--text-secondary)]">
                候选 {{ item.candidate_count }} 只，领涨 {{ item.leading_name || item.leading_symbol || '—' }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="section-label">Recommendation Table</div>
              <h3 class="panel-title mt-3">推荐明细</h3>
              <p class="panel-subtitle">按最近成功快照列出全部研究候选。</p>
            </div>
          </div>

          <div v-if="store.recommendations.length === 0" class="compact-empty">暂无推荐明细</div>
          <div v-else class="overflow-x-auto">
            <table class="w-full min-w-[920px] text-left text-sm">
              <thead class="border-b border-white/10 text-[var(--text-tertiary)]">
                <tr>
                  <th class="py-3 pr-4 font-medium">标的</th>
                  <th class="py-3 pr-4 font-medium">分层</th>
                  <th class="py-3 pr-4 font-medium">板块</th>
                  <th class="py-3 pr-4 font-medium">评分</th>
                  <th class="py-3 pr-4 font-medium">价格</th>
                  <th class="py-3 pr-4 font-medium">支撑位</th>
                  <th class="py-3 pr-4 font-medium">ATR 止损位</th>
                  <th class="py-3 font-medium">AI</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in store.recommendations"
                  :key="item.symbol"
                  class="border-b border-white/5 align-top last:border-0"
                >
                  <td class="py-4 pr-4">
                    <div class="font-semibold">{{ item.name }}</div>
                    <div class="mono-data muted-text mt-1">{{ item.code }}</div>
                    <div class="mt-2 text-xs text-[var(--text-tertiary)]">{{ item.reason }}</div>
                  </td>
                  <td class="py-4 pr-4">
                    <div>{{ layerLabel(item.layer) }}</div>
                    <div class="mt-1 text-xs text-[var(--text-tertiary)]">{{ strategyLabel(item.strategy) }}</div>
                  </td>
                  <td class="py-4 pr-4">
                    <div>{{ item.sector || '未分类' }}</div>
                    <div class="mt-1 text-xs text-[var(--text-tertiary)]">排名 {{ item.sector_rank ?? '—' }}</div>
                  </td>
                  <td class="py-4 pr-4">{{ item.score === null ? '—' : item.score.toFixed(1) }}</td>
                  <td class="py-4 pr-4">
                    <div>{{ formatNullableCurrency(item.price) }}</div>
                    <div :class="['mt-1 text-xs', toneClass(item.change_pct)]">{{ formatSignedPercent(item.change_pct) }}</div>
                  </td>
                  <td class="py-4 pr-4">
                    <div>{{ item.support_type ? `${supportLabel(item.support_type)} · ${formatNullableCurrency(item.support_price)}` : '—' }}</div>
                    <div class="mt-1 text-xs text-[var(--text-tertiary)]">
                      {{ item.support_distance_pct === null ? '—' : `距离 ${item.support_distance_pct.toFixed(2)}%` }}
                    </div>
                  </td>
                  <td class="py-4 pr-4">{{ formatNullableCurrency(item.atr_stop_loss) }}</td>
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

        <div class="panel space-y-4">
          <div class="panel-header !mb-0">
            <div>
              <div class="section-label">Risk Note</div>
              <h3 class="panel-title mt-3">风控说明</h3>
              <p class="panel-subtitle">规则研究只负责筛选，不落地自动交易或持仓写入。</p>
            </div>
          </div>

          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4 text-sm text-[var(--text-secondary)]">
            <div>1. 超跌类更容易高波动，优先关注止损位与情绪拐点。</div>
            <div class="mt-2">2. 支撑类观察承接有效性，不等于支撑一定有效。</div>
            <div class="mt-2">3. 强势回调类优先结合板块排名与均线结构继续验证。</div>
          </div>

          <div class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4">
            <div class="text-sm font-semibold">最近任务历史</div>
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
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { RouterLink } from 'vue-router'

import ErrorAlert from '../components/ErrorAlert.vue'
import PageHeader from '../components/PageHeader.vue'
import { useMarketStore } from '../stores/market'
import { formatCurrency, formatDateTime } from '../utils/format'

const store = useMarketStore()
const activeRun = computed(() => store.latestTask ?? store.snapshot)
const latestStatus = computed(() => store.latestTask?.status ?? store.snapshot?.status ?? 'queued')
const snapshotTimeLabel = computed(() => (store.snapshot?.generated_at ? formatDateTime(store.snapshot.generated_at) : '暂无快照'))
const latestStartedAt = computed(() => store.latestTask?.started_at ?? store.snapshot?.started_at ?? null)
const latestFinishedAt = computed(() => store.latestTask?.finished_at ?? store.snapshot?.finished_at ?? null)
const taskFeedback = computed(() => store.latestTask?.error_message || store.triggerMessage || '无额外错误信息')
const triggerMessage = computed(() => store.triggerMessage || '无额外错误信息')

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

function formatNetInflow(value: number | null): string {
  if (value === null) {
    return '暂无'
  }
  const abs = Math.abs(value)
  const sign = value >= 0 ? '+' : '-'
  if (abs >= 100000000) {
    return `${sign}${(abs / 100000000).toFixed(2)} 亿`
  }
  return `${sign}${(abs / 10000).toFixed(2)} 万`
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

function layerLabel(layer: string | null): string {
  const mapping: Record<string, string> = {
    oversold: '超跌',
    support: '支撑',
    pullback: '回调',
  }
  return layer ? mapping[layer] ?? layer : '观察'
}

function strategyLabel(strategy: string | null): string {
  const mapping: Record<string, string> = {
    oversold_reversal: '超跌低吸',
    support_retest: '支撑观察',
    trend_pullback: '强势回调',
  }
  return strategy ? mapping[strategy] ?? strategy : '观察样本'
}

function supportLabel(type: string): string {
  const mapping: Record<string, string> = {
    ma10: '10 日线',
    ma20: '20 日线',
    swing_low: '波段低点',
  }
  return mapping[type] ?? type
}

async function reload(): Promise<void> {
  await store.loadResearchReport()
}

async function runResearch(): Promise<void> {
  await store.triggerResearchRun()
}

onMounted(() => {
  void reload()
})

onBeforeUnmount(() => {
  store.clearPoll()
})
</script>
