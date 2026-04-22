<template>
  <section class="flex flex-col gap-6">
    <div>
      <h2 class="page-title">仪表盘</h2>
      <p class="page-subtitle">
        聚合默认账户的资产、持仓、订单和收益情况，用于快速确认主链路是否已经跑通。
      </p>
    </div>

    <el-alert
      v-if="errorMessage"
      :closable="false"
      :title="errorMessage"
      type="warning"
      show-icon
    />

    <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      <el-card v-for="item in metricCards" :key="item.label" class="surface-card metric-card">
        <div class="metric-label">{{ item.label }}</div>
        <div class="metric-value" :class="item.emphasisClass">{{ item.value }}</div>
        <div class="metric-hint">{{ item.hint }}</div>
      </el-card>
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1.5fr_1fr]">
      <el-card class="surface-card">
        <template #header>
          <div class="flex items-center justify-between gap-4">
            <span class="font-semibold">资产曲线</span>
            <el-button text @click="loadDashboard">刷新</el-button>
          </div>
        </template>

        <div v-loading="loading" ref="equityChartRef" class="h-72 w-full"></div>
      </el-card>

      <el-card class="surface-card">
        <template #header>
          <div class="font-semibold">账户概览</div>
        </template>

        <div class="space-y-3 text-sm">
          <div class="flex items-center justify-between">
            <span class="muted-text">账户名称</span>
            <span>{{ primaryAccount?.name ?? '默认模拟账户' }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="muted-text">账户状态</span>
            <el-tag class="pill-tag" :type="primaryAccount?.status === 'active' ? 'success' : 'warning'">
              {{ primaryAccount?.status === 'active' ? '可交易' : '暂停' }}
            </el-tag>
          </div>
          <div class="flex items-center justify-between">
            <span class="muted-text">币种</span>
            <span>{{ primaryAccount?.currency ?? 'CNY' }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="muted-text">持仓数量</span>
            <span>{{ positions.length }} 只</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="muted-text">订单总数</span>
            <span>{{ orders.length }} 笔</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="muted-text">最近更新时间</span>
            <span>{{ lastUpdated }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_1fr]">
      <el-card class="surface-card">
        <template #header>
          <div class="font-semibold">最近订单</div>
        </template>

        <el-table :data="recentOrders" stripe empty-text="暂无订单数据">
          <el-table-column prop="symbol" label="代码" min-width="120" />
          <el-table-column label="方向" min-width="100">
            <template #default="{ row }">
              <el-tag class="pill-tag" :type="row.side === 'buy' ? 'danger' : 'success'">
                {{ row.side === 'buy' ? '买入' : '卖出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="110">
            <template #default="{ row }">
              <el-tag class="pill-tag" :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="filled_quantity" label="成交数量" min-width="100" />
          <el-table-column label="成交价" min-width="120">
            <template #default="{ row }">{{ formatCurrency(row.filled_price) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card class="surface-card">
        <template #header>
          <div class="font-semibold">持仓摘要</div>
        </template>

        <div v-if="positions.length === 0" class="muted-text text-sm">暂无持仓，先去“交易与持仓”页面提交一笔买单。</div>
        <div v-else class="space-y-4">
          <div
            v-for="position in positions.slice(0, 5)"
            :key="position.id"
            class="rounded-2xl border border-[var(--border)] bg-white/60 px-4 py-3"
          >
            <div class="flex items-center justify-between">
              <div>
                <div class="font-semibold">{{ position.symbol }}</div>
                <div class="muted-text text-xs">持仓 {{ position.quantity }} 股</div>
              </div>
              <div class="text-right">
                <div>{{ formatCurrency(position.last_price) }}</div>
                <div :class="Number(position.unrealized_pnl) >= 0 ? 'text-emerald-600' : 'text-rose-600'">
                  {{ formatCurrency(position.unrealized_pnl) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <el-card class="surface-card">
      <template #header>
        <div class="font-semibold">月度绩效</div>
      </template>

      <el-table :data="monthlyStats" stripe empty-text="暂无月度绩效数据">
        <el-table-column prop="period" label="月份" min-width="120" />
        <el-table-column prop="trade_count" label="成交次数" min-width="100" />
        <el-table-column label="已实现盈亏" min-width="140">
          <template #default="{ row }">
            <span :class="row.realized_pnl >= 0 ? 'text-emerald-600' : 'text-rose-600'">
              {{ formatCurrency(row.realized_pnl) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="期末总资产" min-width="160">
          <template #default="{ row }">{{ formatCurrency(row.ending_equity) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchAccounts, type AccountItem } from '../api/accounts'
import { fetchOrders, type OrderItem } from '../api/orders'
import { fetchPortfolioSummary, type PortfolioSummary } from '../api/portfolio'
import {
  fetchEquityCurve,
  fetchMonthlyStats,
  fetchReportingSummary,
  type EquityCurvePoint,
  type PeriodStat,
  type ReportingSummary,
} from '../api/reporting'
import { fetchPositions, type PositionItem } from '../api/positions'
import { formatCurrency, formatDateTime, formatPercent } from '../utils/format'
import { getApiErrorMessage } from '../utils/http'

const equityChartRef = ref<HTMLDivElement | null>(null)
let equityChart: { dispose: () => void; resize: () => void; setOption: (option: object) => void } | null = null
let echartsModule: { init: (element: HTMLDivElement) => { dispose: () => void; resize: () => void; setOption: (option: object) => void } } | null = null

const loading = ref(true)
const errorMessage = ref('')
const summary = ref<PortfolioSummary>({
  total_equity: 0,
  available_cash: 0,
  frozen_cash: 0,
  market_value: 0,
  unrealized_pnl: 0,
})
const reporting = ref<ReportingSummary>({
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
const orders = ref<OrderItem[]>([])
const positions = ref<PositionItem[]>([])
const accounts = ref<AccountItem[]>([])
const lastUpdated = ref('未刷新')

const primaryAccount = computed(() => accounts.value[0])
const recentOrders = computed(() => orders.value.slice(0, 5))
const metricCards = computed(() => [
  {
    label: '总资产',
    value: formatCurrency(summary.value.total_equity),
    hint: `累计收益 ${formatPercent(reporting.value.cumulative_return)}`,
    emphasisClass: '',
  },
  {
    label: '可用资金',
    value: formatCurrency(summary.value.available_cash),
    hint: `冻结资金 ${formatCurrency(summary.value.frozen_cash)}`,
    emphasisClass: '',
  },
  {
    label: '持仓市值',
    value: formatCurrency(summary.value.market_value),
    hint: `当前持仓 ${positions.value.length} 只`,
    emphasisClass: '',
  },
  {
    label: '已实现盈亏',
    value: formatCurrency(reporting.value.realized_pnl),
    hint: `胜率 ${formatPercent(reporting.value.win_rate)}`,
    emphasisClass: reporting.value.realized_pnl >= 0 ? 'text-emerald-700' : 'text-rose-700',
  },
])

onMounted(() => {
  void loadDashboard()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  equityChart?.dispose()
  equityChart = null
})

async function loadDashboard(): Promise<void> {
  loading.value = true
  errorMessage.value = ''

  try {
    const [
      accountData,
      summaryData,
      reportingData,
      curveData,
      monthlyData,
      orderData,
      positionData,
    ] = await Promise.all([
      fetchAccounts(),
      fetchPortfolioSummary(),
      fetchReportingSummary(),
      fetchEquityCurve(),
      fetchMonthlyStats(),
      fetchOrders(),
      fetchPositions(),
    ])

    accounts.value = accountData
    summary.value = summaryData
    reporting.value = reportingData
    orders.value = orderData
    positions.value = positionData
    monthlyStats.value = monthlyData
    equityCurve.value = curveData.length > 0 ? curveData : [
      { label: '当前', total_equity: summaryData.total_equity },
    ]
    lastUpdated.value = formatDateTime(new Date().toISOString())

    await nextTick()
    await renderEquityChart()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '仪表盘数据加载失败')
  } finally {
    loading.value = false
  }
}

async function renderEquityChart(): Promise<void> {
  if (!equityChartRef.value) {
    return
  }

  if (!echartsModule) {
    const [{ init, use }, { LineChart }, { GridComponent, TooltipComponent }, { CanvasRenderer }] = await Promise.all([
      import('echarts/core'),
      import('echarts/charts'),
      import('echarts/components'),
      import('echarts/renderers'),
    ])
    use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
    echartsModule = { init }
  }

  if (!equityChart) {
    equityChart = echartsModule.init(equityChartRef.value)
  }

  equityChart.setOption({
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: number) => formatCurrency(value),
    },
    grid: {
      left: 48,
      right: 20,
      top: 20,
      bottom: 30,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: equityCurve.value.map((point) => point.label),
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {
        formatter: (value: number) => `${Math.round(value / 1000)}k`,
      },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: 3,
          color: '#0f766e',
        },
        areaStyle: {
          color: 'rgba(15, 118, 110, 0.12)',
        },
        data: equityCurve.value.map((point) => point.total_equity),
      },
    ],
  })
}

function handleResize(): void {
  equityChart?.resize()
}

function statusLabel(status: OrderItem['status']): string {
  const mapping: Record<OrderItem['status'], string> = {
    pending: '挂单中',
    filled: '已成交',
    rejected: '已拒绝',
    cancelled: '已撤销',
  }
  return mapping[status]
}

function statusTagType(status: OrderItem['status']): 'info' | 'success' | 'warning' | 'danger' {
  if (status === 'filled') {
    return 'success'
  }
  if (status === 'pending') {
    return 'warning'
  }
  if (status === 'cancelled') {
    return 'info'
  }
  return 'danger'
}
</script>
