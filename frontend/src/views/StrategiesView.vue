<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <PageHeader
        title="策略中心"
        subtitle="聚焦真实策略定义、运行结果和启停状态，不再展示随机演示指标。"
      />
      <button class="secondary-button" type="button" :disabled="store.loading" @click="loadStrategies">
        刷新策略
      </button>
    </div>

    <ErrorAlert :message="store.error" type="error" />

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="策略总数" :value="store.strategyCount" hint="数据库中的全部策略" />
      <MetricCard label="启用中" :value="store.activeStrategies.length" hint="status = active" emphasis-class="value-positive" />
      <MetricCard label="今日运行次数" :value="todayRunsTotal" hint="所有策略 run_count_today 汇总" />
      <MetricCard label="已有运行结果" :value="strategiesWithRuns" hint="total_run_count > 0 的策略数" />
    </div>

    <div class="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">策略全景表</h3>
            <p class="panel-subtitle">状态、标的、最新信号、运行次数和最近执行时间全部来自后端真实字段。</p>
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
                <th>标的</th>
                <th>最新信号</th>
                <th>今日运行</th>
                <th>累计运行</th>
                <th>最近运行</th>
                <th>操作</th>
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
                    {{ strategy.status === 'active' ? '启用中' : '已暂停' }}
                  </span>
                </td>
                <td>
                  <div class="mono-data">{{ strategy.signal_symbol }}</div>
                  <div class="text-xs text-[var(--text-tertiary)]">{{ strategy.symbol }}</div>
                </td>
                <td>
                  <span :class="['status-chip', signalTone(strategy.latest_signal)]">
                    {{ signalLabel(strategy.latest_signal) }}
                  </span>
                  <div class="mt-1 text-xs text-[var(--text-tertiary)]">
                    {{ strategy.latest_run_status ? runStatusLabel(strategy.latest_run_status) : '尚未运行' }}
                  </div>
                </td>
                <td class="mono-data">{{ strategy.run_count_today }}</td>
                <td class="mono-data">{{ strategy.total_run_count }}</td>
                <td class="mono-data">{{ formatTime(strategy.latest_run_at) }}</td>
                <td>
                  <div class="flex flex-wrap gap-2">
                    <button
                      class="secondary-button !min-h-9 px-3 text-xs"
                      type="button"
                      :disabled="store.loading"
                      @click="handleRun(strategy.id)"
                    >
                      运行一次
                    </button>
                    <button
                      class="ghost-button !min-h-9 px-3 text-xs"
                      type="button"
                      :disabled="store.loading"
                      @click="toggleStrategy(strategy)"
                    >
                      {{ strategy.status === 'active' ? '暂停' : '启用' }}
                    </button>
                  </div>
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
            <p class="panel-subtitle">适合快速查看哪些策略最近真的跑过，以及用了什么参数。</p>
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
                <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ strategy.signal_symbol }}</div>
              </div>
              <span :class="['status-chip', signalTone(strategy.latest_signal)]">
                {{ signalLabel(strategy.latest_signal) }}
              </span>
            </div>

            <div class="mt-4 grid grid-cols-3 gap-3 text-sm">
              <div>
                <div class="muted-text">今日运行</div>
                <div class="mt-1 mono-data">{{ strategy.run_count_today }}</div>
              </div>
              <div>
                <div class="muted-text">累计运行</div>
                <div class="mt-1 mono-data">{{ strategy.total_run_count }}</div>
              </div>
              <div>
                <div class="muted-text">最近状态</div>
                <div class="mt-1 mono-data">{{ strategy.latest_run_status ? runStatusLabel(strategy.latest_run_status) : '未运行' }}</div>
              </div>
            </div>

            <div class="mt-4 text-xs text-[var(--text-tertiary)]">
              最近运行：{{ formatTime(strategy.latest_run_at) }}
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

const todayRunsTotal = computed(() => store.strategies.reduce((sum, strategy) => sum + strategy.run_count_today, 0))
const strategiesWithRuns = computed(() => store.strategies.filter((strategy) => strategy.total_run_count > 0).length)

onMounted(() => {
  void loadStrategies()
})

async function loadStrategies(): Promise<void> {
  await store.fetchStrategies()
}

async function handleRun(strategyId: number): Promise<void> {
  await store.runStrategy(strategyId)
}

async function toggleStrategy(strategy: StrategyItem): Promise<void> {
  const nextStatus = strategy.status === 'active' ? 'paused' : 'active'
  await store.setStrategyStatus(strategy.id, nextStatus)
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

function runStatusLabel(status: string): string {
  const mapping: Record<string, string> = {
    pending: '排队中',
    success: '成功',
    failed: '失败',
  }
  return mapping[status] ?? status
}

function formatParameters(parameters: StrategyItem['parameters']): string[] {
  return Object.entries(parameters).map(([key, value]) => `${key}: ${value}`)
}

function formatTime(timestamp: string | null): string {
  if (!timestamp) {
    return '尚未运行'
  }
  return new Date(timestamp).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
</script>
