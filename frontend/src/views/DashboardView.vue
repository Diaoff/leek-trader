<template>
  <div class="grid grid-cols-12 gap-4">
    <!-- 左侧状态栏 -->
    <div class="col-span-12 lg:col-span-2">
      <el-card class="mb-4">
        <div class="text-center mb-4">
          <div class="flex items-center justify-center gap-2 mb-2">
            <el-icon class="text-success"><Check /></el-icon>
            <span class="font-semibold">运行中</span>
          </div>
          <div class="text-xs text-dark-text-secondary">系统运行中</div>
        </div>
        <div class="space-y-2 text-sm">
          <div class="flex justify-between">
            <span>运行时间</span>
            <span>{{ systemInfo.runtime }}</span>
          </div>
          <div class="flex justify-between">
            <span>今日任务</span>
            <span>{{ systemInfo.todayTasks }} 任务</span>
          </div>
          <div class="flex justify-between">
            <span>下次启动</span>
            <span>{{ systemInfo.nextRun }}</span>
          </div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="font-semibold">今日交易追踪</div>
        </template>
        <div class="space-y-2 text-sm">
          <div
            v-for="(trade, index) in tradeTracking"
            :key="index"
            class="flex justify-between items-center"
          >
            <span>{{ trade.time }}</span>
            <span class="text-xs text-dark-text-secondary">{{ trade.action }} - {{ trade.status }}</span>
          </div>
          <div v-if="tradeTracking.length === 0" class="text-xs text-dark-text-secondary">
            暂无交易记录
          </div>
        </div>
      </el-card>
    </div>

    <!-- 主内容区 -->
    <div class="col-span-12 lg:col-span-7 space-y-4">
      <!-- 财务指标 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <el-card>
          <div class="text-xs text-dark-text-secondary">总资产</div>
          <div class="mt-1 text-xl font-bold">{{ formatCurrency(summary.total_equity) }}</div>
          <div class="text-xs text-dark-text-secondary">总收益率 {{ formatPercent(reporting.cumulative_return) }}</div>
        </el-card>
        <el-card>
          <div class="text-xs text-dark-text-secondary">可用资金</div>
          <div class="mt-1 text-xl font-bold">{{ formatCurrency(summary.available_cash) }}</div>
          <div class="text-xs text-dark-text-secondary">占比 {{ calculateRatio(summary.available_cash, summary.total_equity) }}%</div>
        </el-card>
        <el-card>
          <div class="text-xs text-dark-text-secondary">持仓市值</div>
          <div class="mt-1 text-xl font-bold">{{ formatCurrency(summary.market_value) }}</div>
          <div class="text-xs text-dark-text-secondary">占比 {{ calculateRatio(summary.market_value, summary.total_equity) }}%</div>
        </el-card>
        <el-card>
          <div class="text-xs text-dark-text-secondary">浮动盈亏</div>
          <div class="mt-1 text-xl font-bold" :class="summary.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'">
            {{ formatCurrency(summary.unrealized_pnl) }}
          </div>
          <div class="text-xs text-dark-text-secondary">收益率 {{ formatPercent(summary.unrealized_pnl_ratio) }}</div>
        </el-card>
      </div>

      <!-- 交易统计 -->
      <el-card>
        <template #header>
          <div class="flex justify-between items-center">
            <div class="font-semibold">交易统计</div>
            <div class="flex gap-4 text-xs">
              <span>失败订单 {{ systemStatus.failedOrders }}</span>
              <span>执行中 {{ systemStatus.executing }}</span>
              <span>排队中 {{ systemStatus.queued }}</span>
              <span>挂起 {{ systemStatus.suspended }}</span>
              <span>今日成交 {{ systemStatus.todayTrades }} 笔</span>
              <span>历史成交 {{ systemStatus.historyTrades }} 笔</span>
            </div>
          </div>
        </template>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <el-card class="bg-dark-bg border-danger">
            <div class="text-sm font-semibold text-danger">买单执行</div>
            <div class="mt-2 text-2xl font-bold">{{ systemStatus.buyOrders }}</div>
            <div class="text-xs text-dark-text-secondary">成功率 {{ systemStatus.buySuccessRate }}%</div>
          </el-card>
          <el-card class="bg-dark-bg border-success">
            <div class="text-sm font-semibold text-success">卖单执行</div>
            <div class="mt-2 text-2xl font-bold">{{ systemStatus.sellOrders }}</div>
            <div class="text-xs text-dark-text-secondary">成功率 {{ systemStatus.sellSuccessRate }}%</div>
          </el-card>
          <el-card class="bg-dark-bg border-info">
            <div class="text-sm font-semibold text-info">策略运行</div>
            <div class="mt-2 text-2xl font-bold">{{ systemStatus.strategyRuns }}</div>
            <div class="text-xs text-dark-text-secondary">成功率 {{ systemStatus.strategySuccessRate }}%</div>
          </el-card>
          <el-card class="bg-dark-bg border-warning">
            <div class="text-sm font-semibold text-warning">风控检查</div>
            <div class="mt-2 text-2xl font-bold">{{ systemStatus.riskChecks }}</div>
            <div class="text-xs text-dark-text-secondary">通过率 {{ systemStatus.riskPassRate }}%</div>
          </el-card>
        </div>
      </el-card>

      <!-- 收益率曲线 -->
      <el-card>
        <template #header>
          <div class="font-semibold">资产曲线</div>
        </template>
        <div ref="equityChartRef" class="h-64 w-full"></div>
      </el-card>

      <!-- 月度统计 -->
      <el-card>
        <template #header>
          <div class="font-semibold">月度统计</div>
        </template>
        <el-table :data="monthlyStats" stripe size="small">
          <el-table-column prop="period" label="月份" min-width="100" />
          <el-table-column prop="trade_count" label="成交次数" min-width="80" />
          <el-table-column prop="realized_pnl" label="已实现盈亏" min-width="120">
            <template #default="scope">
              <span :class="scope.row.realized_pnl >= 0 ? 'text-success' : 'text-danger'">
                {{ formatCurrency(scope.row.realized_pnl) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="ending_equity" label="期末总资产" min-width="140">
            <template #default="scope">
              {{ formatCurrency(scope.row.ending_equity) }}
            </template>
          </el-table-column>
          <el-table-column prop="return_rate" label="收益率" min-width="100">
            <template #default="scope">
              <span :class="scope.row.return_rate >= 0 ? 'text-success' : 'text-danger'">
                {{ formatPercent(scope.row.return_rate) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 右侧状态栏 -->
    <div class="col-span-12 lg:col-span-3 space-y-4">
      <el-card>
        <template #header>
          <div class="font-semibold">账户状态</div>
        </template>
        <div class="space-y-2">
          <div class="flex justify-between items-center">
            <span class="text-sm">账户ID</span>
            <span class="text-sm">{{ accountInfo.accountId }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">账户名称</span>
            <span class="text-sm">{{ accountInfo.accountName }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">账户类型</span>
            <el-tag size="small" type="success">{{ accountInfo.accountType }}</el-tag>
          </div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="font-semibold">持仓状态</div>
        </template>
        <div class="space-y-2">
          <div class="flex justify-between items-center">
            <span class="text-sm">持仓股票</span>
            <span class="text-sm">{{ portfolioStatus.holdingCount }} 只</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">持仓市值</span>
            <span class="text-sm">{{ formatCurrency(portfolioStatus.marketValue) }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">浮动盈亏</span>
            <span class="text-sm" :class="portfolioStatus.unrealizedPnl >= 0 ? 'text-success' : 'text-danger'">
              {{ formatCurrency(portfolioStatus.unrealizedPnl) }}
            </span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">持仓盈亏比</span>
            <span class="text-sm">{{ portfolioStatus.profitRatio }}</span>
          </div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="font-semibold">交易状态</div>
        </template>
        <div class="space-y-2">
          <div class="flex justify-between items-center">
            <span class="text-sm">当前订单</span>
            <span class="text-sm">{{ tradingStatus.currentOrders }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">今日成交</span>
            <span class="text-sm">{{ tradingStatus.todayTrades }} 笔</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">今日买入</span>
            <span class="text-sm">{{ tradingStatus.todayBuy }} 笔</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">今日卖出</span>
            <span class="text-sm">{{ tradingStatus.todaySell }} 笔</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">胜率</span>
            <span class="text-sm">{{ formatPercent(reporting.win_rate) }}</span>
          </div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="font-semibold">风险指标</div>
        </template>
        <div class="space-y-2">
          <div class="flex justify-between items-center">
            <span class="text-sm">最大回撤</span>
            <span class="text-sm text-danger">{{ formatPercent(reporting.max_drawdown) }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">盈亏比</span>
            <span class="text-sm">{{ formatNumber(reporting.profit_factor) }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">平均盈利</span>
            <span class="text-sm text-success">{{ formatCurrency(reporting.avg_win) }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">平均亏损</span>
            <span class="text-sm text-danger">{{ formatCurrency(reporting.avg_loss) }}</span>
          </div>
        </div>
      </el-card>

      <el-card>
        <template #header>
          <div class="font-semibold">资金状况</div>
        </template>
        <div class="space-y-2">
          <div class="flex justify-between items-center">
            <span class="text-sm">总资产</span>
            <span class="text-sm font-bold">{{ formatCurrency(summary.total_equity) }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">可用资金</span>
            <span class="text-sm">{{ formatCurrency(summary.available_cash) }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">冻结资金</span>
            <span class="text-sm">{{ formatCurrency(summary.frozen_cash) }}</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-sm">已实现盈亏</span>
            <span class="text-sm" :class="reporting.realized_pnl >= 0 ? 'text-success' : 'text-danger'">
              {{ formatCurrency(reporting.realized_pnl) }}
            </span>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Check } from '@element-plus/icons-vue'

import { fetchPortfolioSummary } from '../api/portfolio'
import { fetchMonthlyStats, fetchReportingSummary } from '../api/reporting'

const equityChartRef = ref<HTMLDivElement | null>(null)
let equityChart: { dispose: () => void; resize: () => void; setOption: (option: object) => void } | null = null
let echartsModule: { init: (element: HTMLDivElement) => { dispose: () => void; resize: () => void; setOption: (option: object) => void } } | null = null

const summary = ref({
  total_equity: 20130.04,
  available_cash: 9944.04,
  market_value: 10186.00,
  unrealized_pnl: 0.00,
  unrealized_pnl_ratio: 0.0845,
  frozen_cash: 0.00,
})

const reporting = ref({
  trade_count: 0,
  realized_pnl: 0,
  win_rate: 0.65,
  cumulative_return: 0.1567,
  profit_factor: 1.85,
  max_drawdown: 0.12,
  avg_win: 500.00,
  avg_loss: 300.00,
})

const systemInfo = ref({
  runtime: '172.34s',
  todayTasks: 100,
  nextRun: '17:30',
})

const systemStatus = ref({
  failedOrders: 0,
  executing: 0,
  queued: 0,
  suspended: 0,
  todayTrades: 0,
  historyTrades: 0,
  buyOrders: 0,
  buySuccessRate: 0,
  sellOrders: 0,
  sellSuccessRate: 0,
  strategyRuns: 0,
  strategySuccessRate: 0,
  riskChecks: 0,
  riskPassRate: 0,
})

const tradeTracking = ref([
  { time: '10:00', action: '设置执行计划', status: '执行完成' },
  { time: '10:30', action: '执行买入计划', status: '执行完成' },
  { time: '11:30', action: '执行卖出计划', status: '执行完成' },
  { time: '13:30', action: '执行调仓计划', status: '执行完成' },
])

const accountInfo = ref({
  accountId: 'ACC001',
  accountName: '模拟交易账户',
  accountType: '模拟',
})

const portfolioStatus = ref({
  holdingCount: 3,
  marketValue: 10186.00,
  unrealizedPnl: 0.00,
  profitRatio: '1.5:1',
})

const tradingStatus = ref({
  currentOrders: 0,
  todayTrades: 0,
  todayBuy: 0,
  todaySell: 0,
})

const monthlyStats = ref([
  { period: '2024-01', trade_count: 15, realized_pnl: 500.00, ending_equity: 20500.00, return_rate: 0.05 },
  { period: '2024-02', trade_count: 12, realized_pnl: -200.00, ending_equity: 20300.00, return_rate: -0.01 },
  { period: '2024-03', trade_count: 18, realized_pnl: 800.00, ending_equity: 21100.00, return_rate: 0.04 },
])

onMounted(async () => {
  try {
    const [summaryData, reportingData] = await Promise.all([
      fetchPortfolioSummary(),
      fetchReportingSummary(),
    ])
    summary.value = { ...summary.value, ...summaryData }
    reporting.value = { ...reporting.value, ...reportingData }
  } catch (error) {
    console.error('Failed to fetch data:', error)
  }
  await nextTick()
  renderEquityChart()
})

onBeforeUnmount(() => {
  equityChart?.dispose()
  equityChart = null
})

async function renderEquityChart(): Promise<void> {
  if (!equityChartRef.value) return

  if (!echartsModule) {
    const [{ init, use }, { LineChart }, { GridComponent, TooltipComponent, LegendComponent }, { CanvasRenderer }] = await Promise.all([
      import('echarts/core'),
      import('echarts/charts'),
      import('echarts/components'),
      import('echarts/renderers'),
    ])
    use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])
    echartsModule = { init }
  }

  if (!equityChart) {
    equityChart = echartsModule.init(equityChartRef.value)
  }

  equityChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: number) => formatCurrency(value),
    },
    grid: {
      left: 48,
      right: 24,
      top: 24,
      bottom: 40,
    },
    xAxis: {
      type: 'category',
      data: ['2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2024-06'],
      axisLine: { lineStyle: { color: '#333' } },
      axisLabel: { color: '#a0a0a0' },
    },
    yAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: '#333' } },
      axisLabel: {
        color: '#a0a0a0',
        formatter: (value: number) => `${(value / 10000).toFixed(1)}万`,
      },
      splitLine: { lineStyle: { color: '#333' } },
    },
    series: [
      {
        name: '总资产',
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.3 },
        lineStyle: { width: 2, color: '#1890ff' },
        itemStyle: { color: '#1890ff' },
        showSymbol: false,
        data: [20000, 20500, 20300, 21100, 21500, 22000],
      },
    ],
  })
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : '0.00'
}

function calculateRatio(part: number, total: number): string {
  if (total === 0) return '0.00'
  return ((part / total) * 100).toFixed(2)
}
</script>
