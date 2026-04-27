<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="市场总览"
        subtitle="只展示实时盘面核心摘要，聚合指数、强弱榜单与热点候选。"
      />
      <div class="token-row">
        <span class="status-chip subtle">最近同步 {{ store.lastUpdated }}</span>
        <button class="secondary-button" type="button" :disabled="store.loading" @click="reload">
          刷新页面
        </button>
      </div>
    </div>

    <ErrorAlert :message="store.error" type="warning" />

    <div v-if="!store.overview && !store.loading" class="panel empty-state !min-h-[280px]">
      <div>暂无市场总览数据</div>
      <div class="text-sm text-[var(--text-tertiary)]">刷新后会展示指数、强弱榜单和热点候选。</div>
    </div>

    <template v-else-if="store.overview">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="section-label">Overview</div>
            <h3 class="panel-title mt-3">指数快照</h3>
            <p class="panel-subtitle">{{ formatDateTime(store.overview.generated_at) }}</p>
          </div>
          <span class="status-chip subtle">来源 {{ overviewSourceLabel }}</span>
        </div>

        <div class="grid gap-3 md:grid-cols-3">
          <div
            v-for="item in store.overview.indices"
            :key="item.symbol"
            class="rounded-[18px] border border-white/5 bg-white/[0.03] p-4"
          >
            <div class="font-semibold">{{ item.name }}</div>
            <div class="mt-2 mono-data text-2xl font-semibold">{{ formatNullableCurrency(item.price) }}</div>
            <div :class="['mt-2 text-sm font-semibold', toneClass(item.change_percent)]">
              {{ formatSignedPercent(item.change_percent) }}
            </div>
          </div>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-2">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="section-label">Top Movers</div>
              <h3 class="panel-title mt-3">涨幅榜</h3>
              <p class="panel-subtitle">盘中最强动量样本。</p>
            </div>
            <span class="status-chip rise">Top {{ store.overview.top_gainers.length }}</span>
          </div>

          <div v-if="store.overview.top_gainers.length === 0" class="compact-empty">暂无数据</div>
          <div v-else class="space-y-3">
            <div
              v-for="item in store.overview.top_gainers"
              :key="item.symbol"
              class="flex items-center justify-between gap-3 rounded-[16px] border border-white/5 bg-white/[0.03] p-4"
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

        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="section-label">Top Movers</div>
              <h3 class="panel-title mt-3">跌幅榜</h3>
              <p class="panel-subtitle">用于观察风险集中区。</p>
            </div>
            <span class="status-chip fall">Top {{ store.overview.top_losers.length }}</span>
          </div>

          <div v-if="store.overview.top_losers.length === 0" class="compact-empty">暂无数据</div>
          <div v-else class="space-y-3">
            <div
              v-for="item in store.overview.top_losers"
              :key="item.symbol"
              class="flex items-center justify-between gap-3 rounded-[16px] border border-white/5 bg-white/[0.03] p-4"
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

      <div class="grid gap-4 xl:grid-cols-[240px_240px_minmax(0,1fr)]">
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="section-label">Limit Up</div>
              <h3 class="panel-title mt-3">涨停统计</h3>
            </div>
          </div>
          <div class="text-3xl font-semibold value-rise">{{ store.overview.limit_up.total }}</div>
          <div class="mt-3 text-xs text-[var(--text-tertiary)]">基于当前聚合源统计的强势样本。</div>
          <div class="mt-4 space-y-2">
            <div
              v-for="item in store.overview.limit_up.sample"
              :key="item.symbol"
              class="flex items-center justify-between gap-3 text-sm"
            >
              <span>{{ item.name }}</span>
              <span class="mono-data value-rise">{{ formatSignedPercent(item.change_percent) }}</span>
            </div>
            <div v-if="store.overview.limit_up.sample.length === 0" class="compact-empty !min-h-0 !p-0">暂无样本</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="section-label">Limit Down</div>
              <h3 class="panel-title mt-3">跌停统计</h3>
            </div>
          </div>
          <div class="text-3xl font-semibold value-fall">{{ store.overview.limit_down.total }}</div>
          <div class="mt-3 text-xs text-[var(--text-tertiary)]">用于识别情绪退潮或风险出清压力。</div>
          <div class="mt-4 space-y-2">
            <div
              v-for="item in store.overview.limit_down.sample"
              :key="item.symbol"
              class="flex items-center justify-between gap-3 text-sm"
            >
              <span>{{ item.name }}</span>
              <span class="mono-data value-fall">{{ formatSignedPercent(item.change_percent) }}</span>
            </div>
            <div v-if="store.overview.limit_down.sample.length === 0" class="compact-empty !min-h-0 !p-0">暂无样本</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="section-label">Hot Candidates</div>
              <h3 class="panel-title mt-3">热点候选</h3>
              <p class="panel-subtitle">只保留热度候选，不再混入研究快照板块分析。</p>
            </div>
            <span class="status-chip subtle">Top {{ store.overview.hot_stocks.length }}</span>
          </div>

          <div v-if="store.overview.hot_stocks.length === 0" class="compact-empty">暂无热点股</div>
          <div v-else class="grid gap-3 md:grid-cols-2">
            <div
              v-for="item in store.overview.hot_stocks.slice(0, 6)"
              :key="item.symbol"
              class="rounded-[16px] border border-white/5 bg-white/[0.03] p-4"
            >
              <div class="font-semibold">{{ item.name }}</div>
              <div class="mono-data muted-text mt-1">{{ item.code }}</div>
              <div class="mt-2 text-sm text-[var(--text-secondary)]">{{ item.sector || '热点补充' }}</div>
              <div :class="['mt-1 text-sm font-semibold', toneClass(item.change_percent)]">
                {{ formatSignedPercent(item.change_percent) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ErrorAlert from '../components/ErrorAlert.vue'
import PageHeader from '../components/PageHeader.vue'
import { useMarketStore } from '../stores/market'
import { formatCurrency, formatDateTime } from '../utils/format'

const store = useMarketStore()

const overviewSourceLabel = computed(() => store.overview?.breadth_distribution?.source || store.overview?.northbound.source || 'none')

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

async function reload(): Promise<void> {
  await store.loadMarketData()
}

onMounted(() => {
  void reload()
})
</script>
