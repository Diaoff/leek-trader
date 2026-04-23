<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <PageHeader
        title="盈亏复盘"
        subtitle="用权益轨迹、月度盈亏和关键风险指标回看当前模拟交易系统的运行表现。"
      />
      <button class="secondary-button" type="button" :disabled="loading" @click="loadAnalysisData">
        刷新复盘
      </button>
    </div>

    <ErrorAlert :message="error" type="error" />

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        label="累计收益"
        :value="formatCurrency(summary.realized_pnl)"
        :hint="`累计收益率 ${formatPercent(summary.cumulative_return)}`"
        :emphasis-class="summary.realized_pnl >= 0 ? 'value-positive' : 'value-negative'"
      />
      <MetricCard
        label="交易胜率"
        :value="formatPercent(summary.win_rate)"
        :hint="`累计成交 ${summary.trade_count} 笔`"
        :emphasis-class="summary.win_rate >= 0.5 ? 'value-positive' : 'value-warning'"
      />
      <MetricCard
        label="盈利因子"
        :value="summary.profit_factor.toFixed(2)"
        :hint="`平均盈利 ${formatCurrency(summary.avg_win)}`"
        emphasis-class=""
      />
      <MetricCard
        label="最大回撤"
        :value="formatPercent(summary.max_drawdown)"
        :hint="`平均亏损 ${formatCurrency(summary.avg_loss)}`"
        :emphasis-class="summary.max_drawdown <= 0.1 ? 'value-positive' : 'value-negative'"
      />
    </div>

    <div class="grid gap-4 2xl:grid-cols-2">
      <ChartCard
        ref="equityChartRef"
        title="权益轨迹"
        :loading="loading"
        height="h-80"
      />
      <ChartCard
        ref="monthlyChartRef"
        title="月度实现盈亏"
        :loading="loading"
        height="h-80"
      />
    </div>

    <div class="grid gap-4 2xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">月度表现拆解</h3>
            <p class="panel-subtitle">按月份追踪交易笔数、当月盈亏和期末权益。</p>
          </div>
        </div>

        <div v-if="monthlyStats.length === 0" class="empty-state">
          <div>暂无月度统计</div>
          <div class="text-sm text-[var(--text-tertiary)]">等待后端生成 reporting 数据。</div>
        </div>
        <div v-else class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>期间</th>
                <th>交易笔数</th>
                <th>实现盈亏</th>
                <th>期末权益</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in monthlyStats" :key="row.period">
                <td class="mono-data">{{ row.period }}</td>
                <td class="mono-data">{{ row.trade_count }}</td>
                <td :class="['mono-data font-semibold', row.realized_pnl >= 0 ? 'value-positive' : 'value-negative']">
                  {{ formatCurrency(row.realized_pnl) }}
                </td>
                <td class="mono-data">{{ formatCurrency(row.ending_equity) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel space-y-4">
        <div>
          <div class="section-label">Risk Lens</div>
          <h3 class="panel-title mt-3">风险结构</h3>
        </div>

        <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
          <div class="muted-text text-sm">回撤控制</div>
          <div :class="['mt-2 text-3xl font-semibold tracking-[-0.04em]', summary.max_drawdown <= 0.1 ? 'value-positive' : 'value-negative']">
            {{ formatPercent(summary.max_drawdown) }}
          </div>
          <div class="mt-2 text-sm text-[var(--text-tertiary)]">最大回撤越低，说明资金曲线越平稳。</div>
        </div>

        <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
          <div class="muted-text text-sm">盈亏结构</div>
          <div class="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div>
              <div class="muted-text">平均盈利</div>
              <div class="mt-1 mono-data value-positive">{{ formatCurrency(summary.avg_win) }}</div>
            </div>
            <div>
              <div class="muted-text">平均亏损</div>
              <div class="mt-1 mono-data value-negative">{{ formatCurrency(summary.avg_loss) }}</div>
            </div>
            <div>
              <div class="muted-text">胜率</div>
              <div class="mt-1 mono-data">{{ formatPercent(summary.win_rate) }}</div>
            </div>
            <div>
              <div class="muted-text">盈利因子</div>
              <div class="mt-1 mono-data">{{ summary.profit_factor.toFixed(2) }}</div>
            </div>
          </div>
        </div>

        <div class="rounded-[20px] border border-white/5 bg-white/[0.03] p-4">
          <div class="muted-text text-sm">年度滚动统计</div>
          <div v-if="yearlyStats.length === 0" class="mt-3 text-sm text-[var(--text-tertiary)]">
            暂无年度数据。
          </div>
          <div v-else class="mt-3 space-y-3">
            <div
              v-for="row in yearlyStats"
              :key="row.period"
              class="flex items-center justify-between rounded-2xl border border-white/5 px-4 py-3"
            >
              <div>
                <div class="font-semibold">{{ row.period }}</div>
                <div class="text-xs text-[var(--text-tertiary)]">{{ row.trade_count }} 笔交易</div>
              </div>
              <div class="text-right">
                <div :class="['mono-data font-semibold', row.realized_pnl >= 0 ? 'value-positive' : 'value-negative']">
                  {{ formatCurrency(row.realized_pnl) }}
                </div>
                <div class="text-xs text-[var(--text-tertiary)]">权益 {{ formatCurrency(row.ending_equity) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'

import { fetchEquityCurve, fetchMonthlyStats, fetchReportingSummary, fetchYearlyStats } from '../api/reporting'
import type { EquityCurvePoint, PeriodStat, ReportingSummary } from '../types/reporting'
import ChartCard from '../components/ChartCard.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import MetricCard from '../components/MetricCard.vue'
import PageHeader from '../components/PageHeader.vue'
import { formatCurrency, formatPercent } from '../utils/format'

interface ChartCardExpose {
  initChart: () => Promise<void>
  setOption: (option: object) => void
}

const loading = ref(false)
const error = ref('')
const summary = ref<ReportingSummary>({
  trade_count: 0,
  realized_pnl: 0,
  win_rate: 0,
  cumulative_return: 0,
  profit_factor: 0,
  max_drawdown: 0,
  avg_win: 0,
  avg_loss: 0,
})
const equityCurve = ref<EquityCurvePoint[]>([])
const monthlyStats = ref<PeriodStat[]>([])
const yearlyStats = ref<PeriodStat[]>([])

const equityChartRef = ref<ChartCardExpose | null>(null)
const monthlyChartRef = ref<ChartCardExpose | null>(null)

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
      data: equityCurve.value.map((item) => item.label),
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      axisLabel: { color: '#6f86a4' },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: {
        color: '#6f86a4',
        formatter: (value: number) => `${(value / 10000).toFixed(1)}w`,
      },
    },
    series: [
      {
        type: 'line',
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
        data: equityCurve.value.map((item) => item.total_equity),
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
      data: monthlyStats.value.map((item) => item.period),
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
        data: monthlyStats.value.map((item) => item.realized_pnl),
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

async function loadAnalysisData(): Promise<void> {
  loading.value = true
  error.value = ''

  try {
    const [summaryData, curveData, monthlyData, yearlyData] = await Promise.all([
      fetchReportingSummary(),
      fetchEquityCurve(),
      fetchMonthlyStats(),
      fetchYearlyStats(),
    ])
    summary.value = summaryData
    equityCurve.value = curveData
    monthlyStats.value = monthlyData
    yearlyStats.value = yearlyData
    await renderCharts()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '复盘数据加载失败'
  } finally {
    loading.value = false
  }
}

watch(
  () => [equityCurve.value, monthlyStats.value],
  () => {
    void renderCharts()
  },
  { deep: true },
)

onMounted(() => {
  void loadAnalysisData()
})
</script>
