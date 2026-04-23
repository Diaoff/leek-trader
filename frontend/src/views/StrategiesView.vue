<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="策略中心"
        subtitle="集中观察内置策略的运行状态、最新信号和参数结构，不再混入旧版编辑弹层。"
      />
      <button class="secondary-button" type="button" :disabled="store.loading" @click="loadStrategies">
        刷新策略
      </button>
    </div>

    <ErrorAlert :message="store.error" type="error" />

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="策略总数" :value="store.strategyCount" hint="后端返回的全部策略条目" />
      <MetricCard label="启用中" :value="store.activeStrategies.length" hint="status = active" emphasis-class="value-positive" />
      <MetricCard label="今日信号数" :value="todaySignalsTotal" hint="对 active 策略做合计" />
      <MetricCard
        label="平均累计收益"
        :value="averageReturnLabel"
        hint="仅用于前端展示，不写回后端"
        :emphasis-class="averageReturn >= 0 ? 'value-positive' : 'value-negative'"
      />
    </div>

    <div class="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">策略全景表</h3>
            <p class="panel-subtitle">用单表追踪状态、信号和参数，避免旧版碎片化信息层级。</p>
          </div>
        </div>

        <div v-if="store.strategies.length === 0" class="empty-state">
          <div>暂无策略数据</div>
        </div>
        <div v-else class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>策略</th>
                <th>状态</th>
                <th>信号</th>
                <th>标的</th>
                <th>今日信号</th>
                <th>日内收益</th>
                <th>累计收益</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="strategy in store.strategies" :key="strategy.id">
                <td>
                  <div class="font-semibold">{{ strategy.name }}</div>
                  <div class="text-xs text-[var(--text-tertiary)]">{{ strategyTypeLabel(strategy.strategy_type) }}</div>
                </td>
                <td>
                  <span :class="['status-chip', strategy.status === 'active' ? 'positive' : 'neutral']">
                    {{ strategy.status === 'active' ? '启用中' : strategy.status }}
                  </span>
                </td>
                <td>
                  <span :class="['status-chip', signalTone(strategy.latest_signal)]">
                    {{ signalLabel(strategy.latest_signal) }}
                  </span>
                </td>
                <td class="mono-data">{{ strategy.signal_symbol }}</td>
                <td class="mono-data">{{ strategy.todaySignals }}</td>
                <td :class="['mono-data font-semibold', strategy.todayProfit >= 0 ? 'value-positive' : 'value-negative']">
                  {{ strategy.todayProfit.toFixed(2) }}%
                </td>
                <td :class="['mono-data font-semibold', strategy.totalReturn >= 0 ? 'value-positive' : 'value-negative']">
                  {{ strategy.totalReturn.toFixed(2) }}%
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">活跃策略卡片</h3>
            <p class="panel-subtitle">保留高频阅读信息，适合在仪表盘侧栏式浏览。</p>
          </div>
        </div>

        <div v-if="store.activeStrategies.length === 0" class="empty-state !min-h-[320px]">
          <div>当前没有活跃策略</div>
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="strategy in store.activeStrategies"
            :key="strategy.id"
            class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="font-semibold">{{ strategy.name }}</div>
                <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ strategyTypeLabel(strategy.strategy_type) }}</div>
              </div>
              <span :class="['status-chip', signalTone(strategy.latest_signal)]">
                {{ signalLabel(strategy.latest_signal) }}
              </span>
            </div>

            <div class="mt-4 grid grid-cols-3 gap-3 text-sm">
              <div>
                <div class="muted-text">标的</div>
                <div class="mt-1 mono-data">{{ strategy.signal_symbol }}</div>
              </div>
              <div>
                <div class="muted-text">今日信号</div>
                <div class="mt-1 mono-data">{{ strategy.todaySignals }}</div>
              </div>
              <div>
                <div class="muted-text">累计收益</div>
                <div :class="['mt-1 mono-data font-semibold', strategy.totalReturn >= 0 ? 'value-positive' : 'value-negative']">
                  {{ strategy.totalReturn.toFixed(2) }}%
                </div>
              </div>
            </div>

            <div class="mt-4 token-row">
              <span v-for="entry in formatParameters(strategy.parameters)" :key="entry" class="token-chip">
                {{ entry }}
              </span>
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
import MetricCard from '../components/MetricCard.vue'
import PageHeader from '../components/PageHeader.vue'
import { useStrategyStore } from '../stores/strategies'
import type { StrategyItem } from '../types/strategy'

const store = useStrategyStore()

const todaySignalsTotal = computed(() =>
  store.activeStrategies.reduce((sum, strategy) => sum + strategy.todaySignals, 0),
)

const averageReturn = computed(() => {
  if (store.strategies.length === 0) {
    return 0
  }
  return store.strategies.reduce((sum, strategy) => sum + strategy.totalReturn, 0) / store.strategies.length
})

const averageReturnLabel = computed(() => `${averageReturn.value >= 0 ? '+' : ''}${averageReturn.value.toFixed(2)}%`)

onMounted(() => {
  void loadStrategies()
})

async function loadStrategies(): Promise<void> {
  await store.fetchStrategies()
}

function strategyTypeLabel(strategyType: string): string {
  const mapping: Record<string, string> = {
    moving_average: '双均线',
    macd: 'MACD',
  }
  return mapping[strategyType] ?? strategyType
}

function signalLabel(signal: string): string {
  const mapping: Record<string, string> = {
    buy: '买入',
    sell: '卖出',
    hold: '观望',
  }
  return mapping[signal] ?? signal
}

function signalTone(signal: string): 'positive' | 'negative' | 'neutral' {
  if (signal === 'buy') {
    return 'positive'
  }
  if (signal === 'sell') {
    return 'negative'
  }
  return 'neutral'
}

function formatParameters(parameters: StrategyItem['parameters']): string[] {
  return Object.entries(parameters).map(([key, value]) => `${key}: ${value}`)
}
</script>
