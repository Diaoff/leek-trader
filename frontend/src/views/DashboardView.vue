<template>
  <section class="space-y-6">
    <ErrorAlert :message="store.error" type="error" />

    <div class="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_360px]">
      <div class="panel space-y-5">
        <div class="panel-header !mb-0">
          <div>
            <div class="section-label">Capital Snapshot</div>
            <h3 class="panel-title mt-3">账户资金与风险总览</h3>
            <p class="panel-subtitle">
              最近刷新时间 {{ store.lastUpdated }}，用冷峻仪表盘方式压缩展示交易日最关键的四项指标。
            </p>
          </div>
          <button class="secondary-button" type="button" :disabled="store.loading" @click="reload">
            刷新总览
          </button>
        </div>

        <div class="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
          <MetricCard
            v-for="metric in dashboardMetrics"
            :key="metric.label"
            :label="metric.label"
            :value="metric.value"
            :hint="metric.hint"
            :emphasis-class="metric.emphasisClass"
          />
        </div>
      </div>

      <div class="panel">
        <div class="section-label">Desk Pulse</div>
        <h3 class="panel-title mt-3">运行状态</h3>
        <div class="mt-5 space-y-4">
          <div
            v-for="item in operationRows"
            :key="item.label"
            class="flex items-center justify-between gap-4 border-b border-white/5 pb-4 last:border-0 last:pb-0"
          >
            <div>
              <div class="text-sm text-[var(--text-secondary)]">{{ item.label }}</div>
              <div class="mt-1 text-xs text-[var(--text-tertiary)]">{{ item.hint }}</div>
            </div>
            <div :class="['text-right text-sm font-semibold', item.tone]">{{ item.value }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="grid gap-4 2xl:grid-cols-2">
      <ChartCard
        ref="equityChartRef"
        title="总资产曲线"
        refreshable
        refresh-text="同步数据"
        :loading="store.loading"
        height="h-80"
        @refresh="reload"
      />
      <ChartCard
        ref="monthlyChartRef"
        title="月度实现盈亏"
        :loading="store.loading"
        height="h-80"
      />
    </div>

    <div class="grid gap-4 2xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">重点标的监控</h3>
            <p class="panel-subtitle">仅展示当前 watchlist 中标的的最新报价。</p>
          </div>
          <RouterLink class="ghost-button" to="/watchlist">进入盯盘台</RouterLink>
        </div>

        <div v-if="store.watchlist.length === 0" class="empty-state">
          <div>暂无可展示的标的报价</div>
          <div class="text-sm text-[var(--text-tertiary)]">请先在自选盯盘台添加标的。</div>
        </div>
        <div v-else class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>标的</th>
                <th>最新价</th>
                <th>涨跌幅</th>
                <th>成交量</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="quote in store.watchlist.slice(0, 6)" :key="quote.code">
                <td>
                  <div class="font-semibold">{{ quote.name }}</div>
                  <div class="mono-data muted-text mt-1">{{ quote.code }}</div>
                </td>
                <td class="mono-data">{{ formatCurrency(quote.price) }}</td>
                <td :class="['mono-data font-semibold', quoteTone(quote.change_percent)]">
                  {{ formatQuoteChange(quote.change_percent) }}
                </td>
                <td class="mono-data">{{ formatVolume(quote.volume) }}</td>
                <td>
                  <span :class="['status-chip', quote.is_halted ? 'negative' : 'positive']">
                    {{ quote.is_halted ? '停牌' : '交易中' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">活跃策略面板</h3>
            <p class="panel-subtitle">只保留启用中的策略，强调真实信号、运行状态与执行频次。</p>
          </div>
          <RouterLink class="ghost-button" to="/strategies">查看全部策略</RouterLink>
        </div>

        <div v-if="store.activeStrategies.length === 0" class="empty-state !min-h-[260px]">
          <div>当前没有启用中的策略</div>
          <div class="text-sm text-[var(--text-tertiary)]">可在策略中心查看所有内置策略。</div>
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="strategy in store.activeStrategies.slice(0, 5)"
            :key="strategy.id"
            class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="font-semibold">{{ strategy.name }}</div>
                <div class="mt-1 text-sm text-[var(--text-secondary)]">{{ strategy.signal_symbol_display ?? strategy.signal_symbol }}</div>
              </div>
              <span :class="['status-chip', signalTone(strategy.latest_signal)]">
                {{ signalLabel(strategy.latest_signal) }}
              </span>
            </div>
            <div class="mt-4 grid grid-cols-3 gap-3 text-sm">
              <div>
                <div class="muted-text">今日运行</div>
                <div class="mt-1 mono-data font-semibold">{{ strategy.run_count_today }}</div>
              </div>
              <div>
                <div class="muted-text">累计运行</div>
                <div class="mt-1 mono-data font-semibold">{{ strategy.total_run_count }}</div>
              </div>
              <div>
                <div class="muted-text">最近状态</div>
                <div class="mt-1 mono-data font-semibold">
                  {{ strategy.latest_run_status ? runStatusLabel(strategy.latest_run_status) : '未运行' }}
                </div>
              </div>
            </div>
            <div class="mt-3 text-xs text-[var(--text-tertiary)]">
              最近运行：{{ formatDateTime(strategy.latest_run_at) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">最近委托</h3>
          <p class="panel-subtitle">按委托状态和成交数量快速判断撮合进度。</p>
        </div>
        <RouterLink class="ghost-button" to="/portfolio">进入交易台</RouterLink>
      </div>

      <div v-if="store.recentOrders.length === 0" class="empty-state">
        <div>暂无委托记录</div>
        <div class="text-sm text-[var(--text-tertiary)]">在交易页发起第一笔模拟订单。</div>
      </div>
      <div v-else class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>订单</th>
              <th>方向</th>
              <th>状态</th>
              <th>价格</th>
              <th>数量</th>
              <th>成交</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in store.recentOrders" :key="order.id">
              <td>
                <div class="font-semibold">{{ formatSecurityDisplay(order) }}</div>
                <div class="mono-data muted-text mt-1">#{{ order.id }}</div>
              </td>
              <td :class="order.side === 'buy' ? 'value-positive' : 'value-negative'">
                {{ order.side === 'buy' ? '买入' : '卖出' }}
              </td>
              <td>
                <span :class="['status-chip', orderTone(order.status)]">{{ order.status }}</span>
              </td>
              <td class="mono-data">{{ formatCurrency(order.price) }}</td>
              <td class="mono-data">{{ order.quantity }}</td>
              <td class="mono-data">{{ order.filled_quantity }} / {{ order.quantity }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import ChartCard from '../components/ChartCard.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import MetricCard from '../components/MetricCard.vue'
import { useDashboardStore } from '../stores/dashboard'
import { formatChinaDateTime, formatCurrency, formatPercent } from '../utils/format'
import { formatSecurityDisplay } from '../utils/securityDisplay'

interface ChartCardExpose {
  initChart: () => Promise<void>
  setOption: (option: object) => void
}

const store = useDashboardStore()
const equityChartRef = ref<ChartCardExpose | null>(null)
const monthlyChartRef = ref<ChartCardExpose | null>(null)

const dashboardMetrics = computed(() => [
  {
    label: '总资产',
    value: formatCurrency(store.summary.total_equity),
    hint: `累计收益 ${formatPercent(store.reporting.cumulative_return)}`,
    emphasisClass: '',
  },
  {
    label: '可用资金',
    value: formatCurrency(store.summary.available_cash),
    hint: `冻结 ${formatCurrency(store.summary.frozen_cash)}`,
    emphasisClass: '',
  },
  {
    label: '持仓市值',
    value: formatCurrency(store.summary.market_value),
    hint: `${store.positions.length} 个持仓标的`,
    emphasisClass: '',
  },
  {
    label: '已实现盈亏',
    value: formatCurrency(store.reporting.realized_pnl),
    hint: `胜率 ${formatPercent(store.reporting.win_rate)}`,
    emphasisClass: store.reporting.realized_pnl >= 0 ? 'value-rise' : 'value-fall',
  },
])

const operationRows = computed(() => [
  {
    label: '主账户',
    value: store.primaryAccount?.name ?? '默认模拟账户',
    hint: '当前可操作的模拟资金账户',
    tone: '',
  },
  {
    label: '活跃策略',
    value: `${store.activeStrategies.length} 条`,
    hint: '状态为 active 的内置策略',
    tone: 'value-positive',
  },
  {
    label: '交易胜率',
    value: formatPercent(store.reporting.win_rate),
    hint: '已闭环交易的胜率表现',
    tone: store.reporting.win_rate >= 0.5 ? 'value-positive' : 'value-warning',
  },
  {
    label: '最大回撤',
    value: formatPercent(store.reporting.max_drawdown),
    hint: '越低越稳，反映资金曲线回撤深度',
    tone: store.reporting.max_drawdown <= 0.1 ? 'value-positive' : 'value-negative',
  },
])

function formatQuoteChange(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatVolume(value: number): string {
  return new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function quoteTone(value: number): string {
  if (value > 0) {
    return 'value-rise'
  }
  if (value < 0) {
    return 'value-fall'
  }
  return 'muted-text'
}

function signalLabel(signal: string): string {
  const mapping: Record<string, string> = {
    buy: '买入',
    sell: '卖出',
    reduce: '减仓',
    hold: '观望',
  }
  return mapping[signal] ?? signal
}

function signalTone(signal: string): 'positive' | 'negative' | 'neutral' {
  if (signal === 'buy') {
    return 'positive'
  }
  if (signal === 'sell' || signal === 'reduce') {
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

function formatDateTime(value: string | null): string {
  return formatChinaDateTime(value)
}

function orderTone(status: string): 'positive' | 'negative' | 'neutral' {
  if (status === 'filled') {
    return 'positive'
  }
  if (status === 'rejected' || status === 'cancelled') {
    return 'negative'
  }
  return 'neutral'
}

function buildEquityOption(): object {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(7, 14, 25, 0.94)',
      borderColor: 'rgba(121, 168, 220, 0.22)',
      textStyle: { color: '#dbe7f5' },
    },
    grid: { left: 14, right: 18, top: 24, bottom: 20, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: store.equityCurve.map((item) => item.label),
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      axisLabel: { color: '#6f86a4' },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: {
        color: '#6f86a4',
        formatter: (value: number) => `${(value / 10000).toFixed(1)}w`,
      },
    },
    series: [
      {
        type: 'line',
        name: '总资产',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 3, color: '#67b7ff' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(103, 183, 255, 0.34)' },
              { offset: 1, color: 'rgba(103, 183, 255, 0.02)' },
            ],
          },
        },
        data: store.equityCurve.map((item) => item.total_equity),
      },
    ],
  }
}

function buildMonthlyOption(): object {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(7, 14, 25, 0.94)',
      borderColor: 'rgba(121, 168, 220, 0.22)',
      textStyle: { color: '#dbe7f5' },
      valueFormatter: (value: number) => formatCurrency(value),
    },
    grid: { left: 14, right: 18, top: 24, bottom: 20, containLabel: true },
    xAxis: {
      type: 'category',
      data: store.monthlyStats.map((item) => item.period),
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      axisLabel: { color: '#6f86a4' },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: {
        color: '#6f86a4',
        formatter: (value: number) => `${(value / 1000).toFixed(0)}k`,
      },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbolSize: 8,
        lineStyle: { width: 3, color: '#3fd0a4' },
        itemStyle: { color: '#3fd0a4' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(63, 208, 164, 0.28)' },
              { offset: 1, color: 'rgba(63, 208, 164, 0.02)' },
            ],
          },
        },
        data: store.monthlyStats.map((item) => item.realized_pnl),
      },
    ],
  }
}

async function renderCharts(): Promise<void> {
  await nextTick()

  if (equityChartRef.value) {
    await equityChartRef.value.initChart()
    equityChartRef.value.setOption(buildEquityOption())
  }

  if (monthlyChartRef.value) {
    await monthlyChartRef.value.initChart()
    monthlyChartRef.value.setOption(buildMonthlyOption())
  }
}

async function reload(): Promise<void> {
  try {
    await store.loadDashboardData()
    await renderCharts()
  } catch {
    // store.error is already populated in the store
  }
}

watch(
  () => [store.equityCurve, store.monthlyStats],
  () => {
    void renderCharts()
  },
  { deep: true },
)

onMounted(() => {
  void reload()
})
</script>
