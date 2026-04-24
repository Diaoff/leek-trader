<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="市场总览"
        subtitle="聚合指数、涨跌排行、市场情绪与盘面分布，用于快速观察当日市场结构。"
      />
      <div class="token-row">
        <span class="status-chip subtle">最近同步 {{ store.lastUpdated }}</span>
        <button class="secondary-button" type="button" :disabled="store.loading" @click="reload">
          刷新页面
        </button>
      </div>
    </div>

    <ErrorAlert :message="store.error" type="warning" />

    <div class="panel space-y-5">
        <div v-if="sentiment && breadthDistribution" class="grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(420px,0.92fr)]">
          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="text-center">
              <h4 class="text-2xl font-semibold">涨跌趋势</h4>
            </div>

            <div class="mt-8 grid gap-4 md:grid-cols-5">
              <div class="text-center">
                <div class="text-[var(--text-secondary)]">上涨</div>
                <div class="mt-3 text-2xl font-semibold value-rise">{{ breadthDistribution.advancing_count }}</div>
              </div>
              <div class="text-center">
                <div class="text-[var(--text-secondary)]">平盘</div>
                <div class="mt-3 text-2xl font-semibold text-[#7c5cff]">{{ breadthDistribution.flat_count }}</div>
              </div>
              <div class="text-center">
                <div class="text-[var(--text-secondary)]">下跌</div>
                <div class="mt-3 text-2xl font-semibold value-fall">{{ breadthDistribution.declining_count }}</div>
              </div>
              <div class="text-center">
                <div class="text-[var(--text-secondary)]">涨停</div>
                <div class="mt-3 text-2xl font-semibold value-rise">{{ sentiment.limit_up_count }}</div>
              </div>
              <div class="text-center">
                <div class="text-[var(--text-secondary)]">跌停</div>
                <div class="mt-3 text-2xl font-semibold value-fall">{{ sentiment.limit_down_count }}</div>
              </div>
            </div>

            <div class="mt-10 text-center">
              <h4 class="text-2xl font-semibold">成交额</h4>
            </div>

            <div class="mt-8 grid gap-4 md:grid-cols-4">
              <div class="text-center">
                <div class="text-[var(--text-secondary)]">当日成交额</div>
                <div class="mt-3 text-2xl font-semibold">{{ formatMarketAmount(turnoverSummary?.today_amount ?? null) }}</div>
              </div>
              <div class="text-center">
                <div class="text-[var(--text-secondary)]">昨日成交</div>
                <div class="mt-3 text-2xl font-semibold">{{ formatMarketAmount(turnoverSummary?.previous_day_amount ?? null) }}</div>
              </div>
              <div class="text-center">
                <div class="text-[var(--text-secondary)]">较昨日变动</div>
                <div :class="['mt-3 text-2xl font-semibold', amountToneClass(turnoverSummary?.delta_amount ?? null)]">
                  {{ formatAmountDelta(turnoverSummary?.delta_amount ?? null) }}
                </div>
              </div>
              <div class="text-center">
                <div class="text-[var(--text-secondary)]">预测全天</div>
                <div class="mt-3 text-2xl font-semibold">{{ formatMarketAmount(turnoverSummary?.estimated_full_day_amount ?? null) }}</div>
              </div>
            </div>
          </div>

          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="breadth-chart">
              <div class="breadth-grid">
                <div v-for="line in 4" :key="line" class="breadth-grid-line" />
              </div>
              <div class="breadth-bars">
                <div
                  v-for="bucket in breadthDistribution.buckets"
                  :key="bucket.key"
                  class="breadth-bar-column"
                >
                  <div class="breadth-bar-value">{{ bucket.count }}</div>
                  <div class="breadth-bar-shell">
                    <div
                      :class="['breadth-bar', bucket.tone]"
                      :style="{ height: barHeight(bucket.count) }"
                    />
                  </div>
                  <div class="breadth-bar-label">{{ bucket.label }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="sentiment" class="grid gap-3 xl:grid-cols-[minmax(0,1fr)_280px]">
          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h4 class="text-sm font-semibold">市场情绪</h4>
                <p class="mt-1 text-xs text-[var(--text-tertiary)]">{{ sentiment.summary }}</p>
              </div>
              <span :class="['status-chip', sentimentTone(sentiment.label)]">{{ sentiment.title }}</span>
            </div>

            <div class="mt-4 grid gap-3 md:grid-cols-3">
              <div class="rounded-[16px] border border-white/5 bg-black/10 p-3">
                <div class="muted-text text-xs">情绪分数</div>
                <div class="mt-2 mono-data text-2xl font-semibold">{{ sentiment.score.toFixed(1) }}</div>
              </div>
              <div class="rounded-[16px] border border-white/5 bg-black/10 p-3">
                <div class="muted-text text-xs">上涨 / 下跌</div>
                <div class="mt-2 text-lg font-semibold">
                  <span class="value-rise">{{ sentiment.advancing_count }}</span>
                  <span class="muted-text px-2">/</span>
                  <span class="value-fall">{{ sentiment.declining_count }}</span>
                </div>
              </div>
              <div class="rounded-[16px] border border-white/5 bg-black/10 p-3">
                <div class="muted-text text-xs">筛选模式</div>
                <div class="mt-2 text-lg font-semibold">{{ selectionModeLabel(sentiment.selection_mode) }}</div>
              </div>
            </div>
          </div>

          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="text-sm font-semibold">板块热度前排</div>
            <div v-if="sectorMomentum.length === 0" class="compact-empty">暂无板块聚合结果</div>
            <div v-else class="mt-4 space-y-3">
              <div
                v-for="item in sectorMomentum.slice(0, 5)"
                :key="item.sector"
                class="rounded-[16px] border border-white/5 bg-black/10 p-3"
              >
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <div class="font-semibold">{{ item.rank }}. {{ item.sector }}</div>
                    <div class="mt-1 text-xs text-[var(--text-tertiary)]">
                      领涨 {{ item.leading_name || item.leading_symbol || '—' }}
                    </div>
                  </div>
                  <span :class="['status-chip', item.avg_change_pct >= 0 ? 'rise' : 'fall']">
                    {{ formatSignedPercent(item.avg_change_pct) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="store.overview">
          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h4 class="text-sm font-semibold">指数快照</h4>
                <p class="mt-1 text-xs text-[var(--text-tertiary)]">
                  {{ formatDateTime(store.overview.generated_at) }}
                </p>
              </div>
              <span class="status-chip subtle">北向 {{ formatNetInflow(store.overview.northbound.net_inflow) }}</span>
            </div>

            <div class="mt-4 grid gap-3 md:grid-cols-3">
              <div
                v-for="item in store.overview.indices"
                :key="item.symbol"
                class="rounded-[16px] border border-white/5 bg-black/10 p-3"
              >
                <div class="font-semibold">{{ item.name }}</div>
                <div class="mt-2 mono-data">{{ formatNullableCurrency(item.price) }}</div>
                <div :class="['mt-1 text-sm font-semibold', toneClass(item.change_percent)]">
                  {{ formatSignedPercent(item.change_percent) }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="store.overview" class="grid gap-4 xl:grid-cols-2">
          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h4 class="text-sm font-semibold">涨幅榜</h4>
                <p class="mt-1 text-xs text-[var(--text-tertiary)]">盘中最强动量样本</p>
              </div>
              <span class="status-chip rise">Top {{ store.overview.top_gainers.length }}</span>
            </div>
            <div v-if="store.overview.top_gainers.length === 0" class="compact-empty">暂无数据</div>
            <div v-else class="mt-4 space-y-3">
              <div
                v-for="item in store.overview.top_gainers"
                :key="item.symbol"
                class="flex items-center justify-between gap-3 border-b border-white/5 pb-3 last:border-0 last:pb-0"
              >
                <div>
                  <div class="font-semibold">{{ item.name }}</div>
                  <div class="mono-data muted-text mt-1">{{ item.code }}</div>
                </div>
                <div class="text-right">
                  <div class="mono-data">{{ formatNullableCurrency(item.price) }}</div>
                  <div :class="['mt-1 text-sm font-semibold', toneClass(item.change_percent)]">
                    {{ formatSignedPercent(item.change_percent) }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h4 class="text-sm font-semibold">跌幅榜</h4>
                <p class="mt-1 text-xs text-[var(--text-tertiary)]">用来观察风险集中区</p>
              </div>
              <span class="status-chip fall">Top {{ store.overview.top_losers.length }}</span>
            </div>
            <div v-if="store.overview.top_losers.length === 0" class="compact-empty">暂无数据</div>
            <div v-else class="mt-4 space-y-3">
              <div
                v-for="item in store.overview.top_losers"
                :key="item.symbol"
                class="flex items-center justify-between gap-3 border-b border-white/5 pb-3 last:border-0 last:pb-0"
              >
                <div>
                  <div class="font-semibold">{{ item.name }}</div>
                  <div class="mono-data muted-text mt-1">{{ item.code }}</div>
                </div>
                <div class="text-right">
                  <div class="mono-data">{{ formatNullableCurrency(item.price) }}</div>
                  <div :class="['mt-1 text-sm font-semibold', toneClass(item.change_percent)]">
                    {{ formatSignedPercent(item.change_percent) }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="store.overview" class="grid gap-4 xl:grid-cols-[240px_240px_minmax(0,1fr)]">
          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="text-sm text-[var(--text-secondary)]">涨停统计</div>
            <div class="mt-3 text-3xl font-semibold value-rise">{{ store.overview.limit_up.total }}</div>
            <div class="mt-2 text-xs text-[var(--text-tertiary)]">基于当前聚合源统计的强势样本。</div>
            <div class="mt-4 space-y-2">
              <div
                v-for="item in store.overview.limit_up.sample"
                :key="item.symbol"
                class="flex items-center justify-between gap-3 text-sm"
              >
                <span>{{ item.name }}</span>
                <span class="mono-data value-rise">{{ formatSignedPercent(item.change_percent) }}</span>
              </div>
            </div>
          </div>

          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="text-sm text-[var(--text-secondary)]">跌停统计</div>
            <div class="mt-3 text-3xl font-semibold value-fall">{{ store.overview.limit_down.total }}</div>
            <div class="mt-2 text-xs text-[var(--text-tertiary)]">用于识别情绪退潮或风险出清压力。</div>
            <div class="mt-4 space-y-2">
              <div
                v-for="item in store.overview.limit_down.sample"
                :key="item.symbol"
                class="flex items-center justify-between gap-3 text-sm"
              >
                <span>{{ item.name }}</span>
                <span class="mono-data value-fall">{{ formatSignedPercent(item.change_percent) }}</span>
              </div>
            </div>
          </div>

          <div class="rounded-[24px] border border-white/5 bg-white/[0.03] p-5">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h4 class="text-sm font-semibold">热点候选</h4>
                <p class="mt-1 text-xs text-[var(--text-tertiary)]">研究服务会在核心池基础上吸收这里的热度补充。</p>
              </div>
              <span class="status-chip subtle">Top {{ store.overview.hot_stocks.length }}</span>
            </div>

            <div v-if="store.overview.hot_stocks.length === 0" class="compact-empty">暂无热点股</div>
            <div v-else class="mt-4 grid gap-3 md:grid-cols-2">
              <div
                v-for="item in store.overview.hot_stocks.slice(0, 6)"
                :key="item.symbol"
                class="rounded-[16px] border border-white/5 bg-black/10 p-3"
              >
                <div class="font-semibold">{{ item.name }}</div>
                <div class="mono-data muted-text mt-1">{{ item.code }}</div>
                <div class="mt-2 text-sm text-[var(--text-secondary)]">
                  {{ item.sector || '热点补充' }}
                </div>
                <div :class="['mt-1 text-sm font-semibold', toneClass(item.change_percent)]">
                  {{ formatSignedPercent(item.change_percent) }}
                </div>
              </div>
            </div>
          </div>
        </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ErrorAlert from '../components/ErrorAlert.vue'
import PageHeader from '../components/PageHeader.vue'
import { useMarketStore } from '../stores/market'
import type { MarketBreadthDistribution, MarketSentiment, MarketTurnoverSummary, SectorMomentum } from '../types/market'
import { formatCurrency, formatDateTime } from '../utils/format'

const store = useMarketStore()

const sentiment = computed<MarketSentiment | null>(() => store.overview?.market_sentiment ?? store.snapshot?.market_sentiment ?? null)
const breadthDistribution = computed<MarketBreadthDistribution | null>(() => store.overview?.breadth_distribution ?? null)
const turnoverSummary = computed<MarketTurnoverSummary | null>(() => store.overview?.turnover_summary ?? null)
const sectorMomentum = computed<SectorMomentum[]>(() => store.overview?.sector_momentum_top ?? store.snapshot?.sector_momentum_top ?? [])
const breadthMaxCount = computed(() => {
  const buckets = breadthDistribution.value?.buckets ?? []
  return buckets.reduce((max, item) => Math.max(max, item.count), 1)
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

function formatMarketAmount(value: number | null): string {
  if (value === null) {
    return '—'
  }
  const abs = Math.abs(value)
  if (abs >= 100000000) {
    return `${(abs / 100000000).toFixed(0)}亿`
  }
  if (abs >= 10000) {
    return `${(abs / 10000).toFixed(0)}万`
  }
  return `${abs.toFixed(0)}`
}

function formatAmountDelta(value: number | null): string {
  if (value === null) {
    return '—'
  }
  const sign = value >= 0 ? '+' : '-'
  return `${sign}${formatMarketAmount(Math.abs(value))}`
}

function amountToneClass(value: number | null): string {
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

function barHeight(count: number): string {
  if (count <= 0) {
    return '0%'
  }
  const ratio = count / breadthMaxCount.value
  return `${Math.max(ratio * 100, 3)}%`
}

function sentimentTone(label: string): 'positive' | 'neutral' | 'negative' {
  if (label === 'strong') {
    return 'positive'
  }
  if (label === 'weak') {
    return 'negative'
  }
  return 'neutral'
}

function selectionModeLabel(mode: string): string {
  const mapping: Record<string, string> = {
    momentum: '偏趋势',
    balanced: '均衡',
    defensive: '防守',
  }
  return mapping[mode] ?? mode
}

async function reload(): Promise<void> {
  await store.loadMarketData()
}

onMounted(() => {
  void reload()
})
</script>

<style scoped>
.breadth-chart {
  position: relative;
  min-height: 360px;
  padding-top: 24px;
}

.breadth-grid {
  position: absolute;
  inset: 24px 0 32px 0;
  display: grid;
  grid-template-rows: repeat(4, 1fr);
  pointer-events: none;
}

.breadth-grid-line {
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}

.breadth-bars {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 10px;
  height: 100%;
  align-items: end;
}

.breadth-bar-column {
  display: flex;
  min-height: 320px;
  flex-direction: column;
  justify-content: end;
  align-items: center;
  gap: 10px;
}

.breadth-bar-value {
  min-height: 28px;
  color: var(--text-secondary);
  font-size: 0.95rem;
  font-weight: 700;
}

.breadth-bar-shell {
  display: flex;
  width: 100%;
  height: 240px;
  align-items: end;
}

.breadth-bar {
  width: 100%;
  min-height: 2px;
  border-radius: 10px 10px 0 0;
}

.breadth-bar.rise {
  background: linear-gradient(180deg, rgba(255, 74, 74, 0.95) 0%, rgba(245, 58, 58, 0.82) 100%);
}

.breadth-bar.fall {
  background: linear-gradient(180deg, rgba(87, 193, 92, 0.95) 0%, rgba(73, 171, 78, 0.82) 100%);
}

.breadth-bar-label {
  color: var(--text-secondary);
  font-size: 0.85rem;
  text-align: center;
  white-space: nowrap;
}

@media (max-width: 960px) {
  .breadth-chart {
    overflow-x: auto;
  }

  .breadth-bars {
    min-width: 760px;
  }
}
</style>
